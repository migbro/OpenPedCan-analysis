#!/usr/bin/env python


"""
01-cnv-frequencies.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Functions to create copy number variation (CNV) cancer type and study gene-level frequencies for OPenPedCan analyses modules 
"""


__author__ = ('Eric Wafula (wafulae@chop.edu)')
__version__ = '1.0'
__date__ = '12 July 2021'


import os 
import sys
import csv
import json
import uuid
import argparse
import subprocess
import numpy as np
import pandas as pd
from functools import reduce
from collections import OrderedDict


def read_parameters():
     p = argparse.ArgumentParser(description=("The 01-snv-frequencies.py scripts creates copy number variation (CNV) cancer type and study gene-level alterations frequencies table for the OPenPedCan analyses modules."), formatter_class=argparse.RawTextHelpFormatter)
     p.add_argument('HISTOLOGY_FILE', type=str, default=None, help="OPenPedCan histology file (histologies.tsv)\n\n")
     p.add_argument('CNV_FILE', type=str, default=None, help="OPenPedCan CNV consensus file (consensus_wgs_plus_cnvkit_wxs.tsv.gz)\n\n")
     p.add_argument('AC_PRIMARY_TUMORS', type=str, default=None, help="OPenPedCan all cohorts independent primary tumor samples file (independent-specimens.wgswxspanel.primary.prefer.wgs.tsv)\n\n")
     p.add_argument('AC_RELAPSE_TUMORS', type=str, default=None, help="OPenPedCan all cohorts independent relapse tumor samples file (independent-specimens.wgswxspanel.relapse.prefer.wgs.tsv)\n\n")
     p.add_argument('EC_PRIMARY_TUMORS', type=str, default=None, help="OPenPedCan each cohort independent primary tumor samples file (independent-specimens.wgswxspanel.primary.eachcohort.prefer.wgs.tsv)\n\n")
     p.add_argument('EC_RELAPSE_TUMORS', type=str, default=None, help="OPenPedCan each cohort independent relapse tumor samples file (independent-specimens.wgswxspanel.relapse.eachcohort.prefer.wgs.tsv)\n\n")
     p.add_argument('-v', '--version', action='version', version="01-cnv-frequencies.py version {} ({})".format(__version__, __date__), help="Print the current 01-cnv-frequencies.py version and exit\n\n")
     return p.parse_args()


def merge_histology_and_cnv_data(histology_file, cnv_consensus_file):
     # load histology file
     histology_df = pd.read_csv(histology_file, sep="\t", na_filter=False, dtype=str)
     
     # subset histology dataframe for relevant columns
     histology_df = histology_df[["Kids_First_Biospecimen_ID","Kids_First_Participant_ID", "cohort", "cancer_group", "sample_type"]]
     
     # load CNV consensus file
     cnv_df = pd.read_csv(cnv_consensus_file, sep="\t", dtype=str)
     mutations = ["gain", "neutral", "loss", "deep deletion", "amplification"]
     cnv_df = cnv_df[cnv_df['status'].isin(mutations)]
     
     
     # merge subset of histology dataframe to CNV dataframe keeping only sample present in the CNV table (left outer join)
     merged_df = pd.merge(cnv_df, histology_df, how="left", left_on="biospecimen_id", right_on="Kids_First_Biospecimen_ID")
     
     # check if non tumor sample are present in the merged dataframe
     if not np.array_equal(np.array(["Tumor"]), merged_df.sample_type.unique()):
          raise Exception("Merged hsitology-CNV dataframe contains non tumor samples")
     
     # check and drop unknown cancer types (cancer_group == NA)
     row_indices = merged_df[(merged_df["cancer_group"] == "NA")].index
     merged_df.drop(row_indices, inplace=True)
     
     # select and reorder relevant columns
     all_tumors_df = merged_df[["gene_symbol", "ensembl", "status", "copy_number", "ploidy", "cohort", "cancer_group", "Kids_First_Biospecimen_ID", "Kids_First_Participant_ID"]].reset_index()
     return(all_tumors_df)


def get_cancer_groups_and_cohorts(all_tumors_df):
     # group samples by cancer_group and cohort
     cancer_group_cohort_df = all_tumors_df.groupby(["cancer_group", "cohort"])["Kids_First_Biospecimen_ID"].nunique().reset_index()
     cancer_group_cohort_df.columns = ["cancer_group", "cohort", "num_samples"]
     
     # group samples by cancer_group only
     def func(x):
          d = {}
          cohort_list = x["cohort"].unique()
          if len(cohort_list) > 1:
               d["cohort"] = "all_cohorts"
          else:
               d["cohort"] = cohort_list[0]
          d["num_samples"] = x["Kids_First_Biospecimen_ID"].nunique()
          return pd.Series(d, index=["cohort", "num_samples"])
     cancer_group_df = all_tumors_df.groupby(["cancer_group"]).apply(func).reset_index()
     
     # concat cancer_group_cohort_df and cancer_group_df and rremove duplicates
     cancer_group_cohort_df = pd.concat([cancer_group_df, cancer_group_cohort_df], sort=False, ignore_index=True)
     cancer_group_cohort_df.drop_duplicates(inplace=True)
     # these subset dataframe is for testing and need to comment out
     #cancer_group_cohort_df = cancer_group_cohort_df[cancer_group_cohort_df.cancer_group.isin(["CNS Embryonal tumor", "Atypical Teratoid Rhabdoid Tumor"])]
     return(cancer_group_cohort_df)


def compute_variant_frequencies(all_tumors_df, all_cohorts_primary_tumors_file, all_cohorts_relapase_tumors_file, each_cohort_primary_tumors_file, each_cohort_relapase_tumors_file, cancer_group_cohort_df):
     tumor_dfs = {"all_tumors": all_tumors_df}
     # get all cohorts independent primary tumor samples and subset from all tumor sample dataframe
     all_cohorts_primary_tumors_samples_list = list(pd.read_csv(all_cohorts_primary_tumors_file, sep="\t", dtype=str)["Kids_First_Biospecimen_ID"].unique())
     all_cohorts_primary_tumors_df = all_tumors_df[all_tumors_df.Kids_First_Biospecimen_ID.isin(all_cohorts_primary_tumors_samples_list)].reset_index()
     tumor_dfs["all_cohorts_primary_tumors"] = all_cohorts_primary_tumors_df
     
     # get all cohorts independent relapse tumor sample and subset from all tumor samples dataframe
     all_cohorts_relapse_tumors_samples_list = list(pd.read_csv(all_cohorts_relapase_tumors_file, sep="\t", dtype=str)["Kids_First_Biospecimen_ID"].unique())
     all_cohorts_relapse_tumors_df = all_tumors_df[all_tumors_df.Kids_First_Biospecimen_ID.isin(all_cohorts_relapse_tumors_samples_list)].reset_index()
     tumor_dfs["all_cohorts_relapse_tumors"] = all_cohorts_relapse_tumors_df

     # get each cohort independent primary tumor samples and subset from all tumor sample dataframe
     each_cohort_primary_tumors_samples_list = list(pd.read_csv(each_cohort_primary_tumors_file, sep="\t", dtype=str)["Kids_First_Biospecimen_ID"].unique())
     each_cohort_primary_tumors_df = all_tumors_df[all_tumors_df.Kids_First_Biospecimen_ID.isin(each_cohort_primary_tumors_samples_list)].reset_index()
     tumor_dfs["each_cohort_primary_tumors"] = each_cohort_primary_tumors_df
     
     # get each cohort independent relapse tumor sample and subset from all tumor samples dataframe
     each_cohort_relapse_tumors_samples_list = list(pd.read_csv(each_cohort_relapase_tumors_file, sep="\t", dtype=str)["Kids_First_Biospecimen_ID"].unique())
     each_cohort_relapse_tumors_df = all_tumors_df[all_tumors_df.Kids_First_Biospecimen_ID.isin(each_cohort_relapse_tumors_samples_list)].reset_index()
     tumor_dfs["each_cohort_relapse_tumors"] = each_cohort_relapse_tumors_df
     
     # compute variant frequencies for each cancer group per cohort and  cancer group in cohorts
     # for the overal dataset (all tumor samples)  and independent primary/replase tumor samples
     def func(x):
          d = {}
          d["Gene_symbol"] = ",".join(x["gene_symbol"].unique())
          d["total_sample_alterations"] = x["Kids_First_Biospecimen_ID"].nunique()
          d["total_patient_alterations"] = x["Kids_First_Participant_ID"].nunique()
          return(pd.Series(d, index=["Gene_symbol", "total_sample_alterations", "total_patient_alterations"]))
     all_tumors_frequency_dfs = []
     primary_tumors_frequency_dfs = []
     relapse_tumors_frequency_dfs = []
     for row in cancer_group_cohort_df.itertuples(index=False):
          if row.num_samples > 3:
               for df_name, tumor_df in tumor_dfs.items():
                    df = pd.DataFrame()
                    if row.cohort == "all_cohorts":
                         if df_name == "all_cohorts_primary_tumors" or df_name == "all_cohorts_relapse_tumors" or  df_name == "all_tumors":
                              df = tumor_df[(tumor_df["cancer_group"] == row.cancer_group)]
                    else:
                         if df_name == "each_cohort_primary_tumors" or df_name == "each_cohort_relapse_tumors" or  df_name == "all_tumors":
                              df = tumor_df[(tumor_df["cancer_group"] == row.cancer_group) & (tumor_df["cohort"] == row.cohort)]
                    if df.empty:
                         continue
                    num_samples = df["Kids_First_Biospecimen_ID"].nunique()
                    num_patients = df["Kids_First_Participant_ID"].nunique()
                    df = df.groupby(["ensembl", "status"]).apply(func)
                    #df = df.rename_axis(["Gene_Ensembl_ID", "Variant_type"]).reset_index() # doesn't work Docker (python v3.5)
                    df = df.rename_axis(index = {"ensembl": "Gene_Ensembl_ID", "status": "Variant_type"}).reset_index()
                    df["num_patients"] = num_patients
                    for i in df.itertuples():
                         if df_name == "all_tumors":
                              df.at[i.Index, "Total_alterations_over_subjects_in_dataset"] = "{}/{}".format(i.total_patient_alterations, num_patients)
                              df.at[i.Index, "Frequency_in_overall_dataset"] = "{:.2f}%".format((i.total_patient_alterations/num_patients)*100)
                         if df_name == "each_cohort_primary_tumors" or df_name == "each_cohort_relapse_tumors" or df_name == "all_cohorts_primary_tumors" or df_name == "all_cohorts_relapse_tumors":
                              df.at[i.Index, "Total_alterations_over_subjects_in_dataset"] = "{}/{}".format(i.total_sample_alterations, num_samples)
                              df.at[i.Index, "Frequency_in_overall_dataset"] = "{:.2f}%".format((i.total_sample_alterations/num_samples)*100)
                         df.at[i.Index, "Dataset"] = row.cohort
                         df.at[i.Index, "Disease"] = row.cancer_group
                    df = df [["Gene_symbol", "Gene_Ensembl_ID", "Variant_type", "Dataset", "Disease", "Total_alterations_over_subjects_in_dataset", "Frequency_in_overall_dataset"]]
                    if df_name == "each_cohort_primary_tumors" or df_name == "all_cohorts_primary_tumors":
                         primary_tumors_frequency_dfs.append(df)
                    if df_name == "each_cohort_relapse_tumors" or df_name == "all_cohorts_relapse_tumors":
                         relapse_tumors_frequency_dfs.append(df)
                    if df_name == "all_tumors":
                         all_tumors_frequency_dfs.append(df)

                         
     #  merge overal dataset (all tumor samples) and independent primary/replase tumor samples frequencies for cancer groups per cohorts into a single dataframe
     merging_list = []
     # frequencies in overall dataset
     all_tumors_frequency_df = pd.concat(all_tumors_frequency_dfs, sort=False, ignore_index=True)
     merging_list.append(all_tumors_frequency_df)
     # frequencies in independent primary tumors
     primary_tumors_frequency_df = pd.concat(primary_tumors_frequency_dfs, sort=False, ignore_index=True)
     primary_tumors_frequency_df.rename(columns={"Total_alterations_over_subjects_in_dataset": "Total_primary_tumors_mutated_over_primary_tumors_in_dataset", "Frequency_in_overall_dataset": "Frequency_in_primary_tumors"}, inplace=True)
     merging_list.append(primary_tumors_frequency_df)
     # frequencies in independent relapse tumors
     relapse_tumors_frequency_df = pd.concat(relapse_tumors_frequency_dfs, sort=False, ignore_index=True)
     relapse_tumors_frequency_df.rename(columns={"Total_alterations_over_subjects_in_dataset": "Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset", "Frequency_in_overall_dataset": "Frequency_in_relapse_tumors"}, inplace=True)
     merging_list.append(relapse_tumors_frequency_df)
     cnv_frequency_df = reduce(lambda x, y: pd.merge(x, y, how="outer", on=["Gene_symbol", "Gene_Ensembl_ID", "Variant_type", "Dataset", "Disease"]), merging_list).fillna("")
     cnv_frequency_df = cnv_frequency_df.replace({"Total_primary_tumors_mutated_over_primary_tumors_in_dataset": "", "Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset": ""}, "0/0")
     # format null frequency values for ensembl ids without cnv call at least one categories (i.e., overall dataset, primary samples, or relapse samples)
     counts_df = cnv_frequency_df[["Dataset", "Disease", "Total_alterations_over_subjects_in_dataset", "Total_primary_tumors_mutated_over_primary_tumors_in_dataset", "Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset"]].copy(deep=True)
     counts_df["num_patients"] = counts_df["Total_alterations_over_subjects_in_dataset"].str.split("/", n=1, expand=True)[1]
     counts_df["num_primary_samples"] = counts_df["Total_primary_tumors_mutated_over_primary_tumors_in_dataset"].str.split("/", n=1, expand=True)[1]
     counts_df["num_relapse_samples"] = counts_df["Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset"].str.split("/", n=1, expand=True)[1]
     counts_df = counts_df[["Dataset", "Disease", "num_patients", "num_primary_samples", "num_relapse_samples"]].drop_duplicates()
     counts_df = counts_df.groupby(["Dataset", "Disease"]).max().reset_index()
     for row in counts_df.itertuples(index=False):
          cnv_frequency_df.loc[((cnv_frequency_df.Dataset == row.Dataset) & (cnv_frequency_df.Disease == row.Disease) & (cnv_frequency_df.Total_alterations_over_subjects_in_dataset == "0/0")), "Total_alterations_over_subjects_in_dataset"] = "{}/{}".format(0, row.num_patients)
          cnv_frequency_df.loc[cnv_frequency_df.Frequency_in_overall_dataset == "", "Frequency_in_overall_dataset"] = "0.00%"
          cnv_frequency_df.loc[((cnv_frequency_df.Dataset == row.Dataset) & (cnv_frequency_df.Disease == row.Disease) & (cnv_frequency_df.Total_primary_tumors_mutated_over_primary_tumors_in_dataset == "0/0")), "Total_primary_tumors_mutated_over_primary_tumors_in_dataset"] = "{}/{}".format(0, row.num_primary_samples)
          cnv_frequency_df.loc[cnv_frequency_df.Frequency_in_primary_tumors == "", "Frequency_in_primary_tumors"] = "0.00%"
          cnv_frequency_df.loc[((cnv_frequency_df.Dataset == row.Dataset) & (cnv_frequency_df.Disease == row.Disease) & (cnv_frequency_df.Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset == "0/0")), "Total_relapse_tumors_mutated_over_relapse_tumors_in_dataset"] = "{}/{}".format(0, row.num_relapse_samples)
          cnv_frequency_df.loc[cnv_frequency_df.Frequency_in_relapse_tumors == "", "Frequency_in_relapse_tumors"] = "0.00%"
     return(cnv_frequency_df)


def get_annotations(cnv_frequency_df, CNV_FILE):
     # insert variant category annotation column in the CNV frequency dataframe
     cnv_frequency_df["Variant_category"] = cnv_frequency_df.insert(3, "Variant_category", "")
     cnv_frequency_df.fillna("", inplace=True)

     # create module results directory
     results_dir = "results".format(os.path.dirname(__file__))
     if not os.path.exists(results_dir):
          os.mkdir(results_dir)

     # get CNV input parameters
     args = read_parameters()

     # write annotated CNV frequencies results to TSV file
     cnv_freq_tsv = "{}/gene-level-cnv-consensus-mut-freq.tsv".format(results_dir)
     cnv_frequency_df.to_csv(cnv_freq_tsv, sep="\t", index=False, encoding="utf-8")

     # annotate full gene names, OncoKB categories, EFO and MONDO disease accessions, 
     # Oct 2022 - update - Sangeeta Shukla - Removed existing Relevant Molecular Target (PMTL) captured from the long-format-table-utils analysis module
     log_file = "{}/annotator.log".format(results_dir)
     cnv_annot_freq_tsv = "{}/gene-level-cnv-consensus-annotated-mut-freq.tsv".format(results_dir)
     with open(log_file, "w") as log:
          subprocess.run(["Rscript", "--vanilla", "../long-format-table-utils/annotator/annotator-cli.R", "-r", "-c", "Gene_full_name,OncoKB_cancer_gene,OncoKB_oncogene_TSG,EFO,MONDO", "-i", cnv_freq_tsv, "-o", cnv_annot_freq_tsv, "-v"], stdout=log, check=True)

     # columns changes proposed by the FNL:
     cnv_annot_freq_df = pd.read_csv(cnv_annot_freq_tsv, sep="\t", na_filter=False, dtype=str)
     #1 rename "Gene_Ensembl_Id" to "targetFromSourceId", "EFO" to "diseaseFromSourceMappedId"
     cnv_annot_freq_df.rename(columns={"Gene_Ensembl_ID": "targetFromSourceId", "EFO": "diseaseFromSourceMappedId"}, inplace=True)
     #2 add "datatypeId" column  with value for every row set to "somatic_mutation"
     cnv_annot_freq_df["datatypeId"] = "somatic_mutation"
     #3 add "chop_uuid" column - the uuid value for each row should be unique
     cnv_annot_freq_df["chop_uuid"] = [uuid.uuid4() for x in range(len(cnv_annot_freq_df))]
     #4 add "datasourceId" column with value for each row set to "chop_gene_level_cnv"
     cnv_annot_freq_df["datasourceId"] = "chop_gene_level_cnv"
     # rename "all_cohorts" entry for "Dataset" column to "All Cohorts" to improve the view in the final PedOT table to the end user
     cnv_annot_freq_df["Dataset"].replace({"all_cohorts": "All Cohorts"}, inplace=True)
     cnv_annot_freq_df.to_csv(cnv_annot_freq_tsv, sep="\t", index=False, encoding="utf-8")

     # transform annotated CNV frequencies results from TSV to JSONL file
     cnv_annot_freq_jsonl = "{}/gene-level-cnv-consensus-annotated-mut-freq.jsonl".format(results_dir)
     tsv_file = open(cnv_annot_freq_tsv, "r")
     jsonl_file = open(cnv_annot_freq_jsonl, "w")
     reader = csv.DictReader(tsv_file, delimiter="\t")
     headers = reader.fieldnames
     for row in reader:
          row_dict = OrderedDict()
          for header in headers:
               row_dict[header] = row[header]
          json.dump(row_dict, jsonl_file)
          jsonl_file.write("\n")
     tsv_file.close()
     jsonl_file.close()


def main():
     # get input parameters
     args = read_parameters()

     # call functions to compute CNV gene-level and add functional annotations
     all_tumors_df = merge_histology_and_cnv_data(args.HISTOLOGY_FILE, args.CNV_FILE)
     cancer_group_cohort_df = get_cancer_groups_and_cohorts(all_tumors_df)
     cnv_frequency_df = compute_variant_frequencies(all_tumors_df, args.AC_PRIMARY_TUMORS, args.AC_RELAPSE_TUMORS, args.EC_PRIMARY_TUMORS, args.EC_RELAPSE_TUMORS, cancer_group_cohort_df)
     cnv_frequency_df = cnv_frequency_df.drop_duplicates()
     cnv_frequency_df = get_annotations(cnv_frequency_df, args.CNV_FILE)
     sys.exit(0)


if __name__ == "__main__":
     main()	
