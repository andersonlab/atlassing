#!/usr/bin/env python

__author__ = 'Bradley Harris'
__date__ = '2024-08-21'
__version__ = '0.0.1' 

import pandas as pd
import numpy as np
import scanpy as sc
import celltypist
import argparse
import os
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    """Run CLI."""
    parser = argparse.ArgumentParser(
        description="""
            Assesses celltypist autoannotation on the original input data
            """
    )
    parser.add_argument(
        '-h5', '--h5_anndata',
        action='store',
        dest='h5',
        required=True,
        help='Path to h5 AnnData file.'
    )
    
    parser.add_argument(
        '-ctm', '--celltypist_model',
        action='store',
        dest='celltypist_model',
        required=True,
        help='celltypist model'
    )
    
    parser.add_argument(
        '-cc', '--compare_column',
        action='store',
        dest='compare_column',
        required=False,
        help='column to compare annotation to'
    )
    
    parser.add_argument(
        '-o', '--outdir',
        action='store',
        dest='outdir',
        default='.',
        required=False,
        help='Output directory'
    )  
    
    options = parser.parse_args()
    h5 = options.h5
    celltypist_model = options.celltypist_model
    compare_column = options.compare_column
    outdir = options.outdir
    

    # Test
    # h5 = "results/objects/from_irods/adata_PCAd_batched_umap_add_expression.h5ad"
    # celltypist_model = "results/objects/from_irods/Label_1-adata_PCAd_batched_umap_add_expression.pkl"
    # compare_column = "Label_1"
    # outdir = "other_paper_figs"

    # Load the AnnData file.
    print('Loading AnnData')
    adata = sc.read_h5ad(filename=h5)
    
    # use log1p_cp10k
    adata.X = adata.layers['log1p_cp10k']

    # Use gene_symbols
    adata.var['ENS'] = adata.var_names
    adata.var_names = list(adata.var['gene_symbols'])
    adata.var_names_make_unique()
    
    # Run the model
    predictions = celltypist.annotate(adata, model = celltypist_model, majority_voting = False)
    ct_adata = predictions.to_adata()

    if compare_column is not None:
        # Perform dotplot
        sc.settings.figdir=outdir
        celltypist.dotplot(predictions, use_as_reference = compare_column, use_as_prediction = 'predicted_labels', filter_prediction=0.01, save=f"_predicted_labels_vs_{compare_column}_autoannot_filt_prediction_0.01.png")
        celltypist.dotplot(predictions, use_as_reference = compare_column, use_as_prediction = 'predicted_labels', filter_prediction=0, save=f"_predicted_labels_vs_{compare_column}_autoannot.png")

        # Summarise for each cell-type, the proportion of correctly assigned cells
        def calc_proportion_and_next_best(group):
            match_proportion = (group[compare_column] == group['predicted_labels']).mean()
            non_matching = group[group[compare_column] != group['predicted_labels']]
            if len(non_matching) > 0:
                next_best = non_matching['predicted_labels'].mode()[0]
                next_best_prop = (non_matching['predicted_labels'] == next_best).mean()
            else:
                next_best = None
                next_best_prop = None
            return pd.Series({
                'proportion': match_proportion,
                'next_best': next_best,
                'next_best_prop': next_best_prop
            })

        # Group by compare_column and apply the function
        pred_prop = ct_adata.obs.groupby(compare_column).apply(calc_proportion_and_next_best).reset_index()
        pred_prop['manual_lineage'] = pred_prop[compare_column].apply(lambda x: x.split('_')[0] if '_' in x else None)

        # Save
        pred_prop.to_csv(f"{outdir}/original_autoannot_accuracy.txt", index=False, sep = "\t")
        
        # Plot distribution of the next best, colored by the manual lineage
        lins = np.unique(pred_prop['manual_lineage'].astype(str))
        plt.figure(figsize=(8, 6))
        fig,ax = plt.subplots(figsize=(8,6))
        for l in lins:
            print(l)
            data = pred_prop.loc[pred_prop['manual_lineage'] == l, "proportion"].values
            sns.distplot(data, hist=False, rug=True, label=l)

        plt.legend()
        plt.xlabel("Proportion of correct annotations per cluster")
        plt.title(f"No absolute cut off")
        plt.savefig(f"{outdir}/celltypist_accuracy_distribution.png", bbox_inches='tight')
        plt.clf()

    # Save the celltypist output
    ct_adata.write_h5ad(f"{outdir}/celltypist_prediction.h5ad")
    
    # Quantifying accuracy
    # Calculate the proportion of correct predictions per annotation
    ct_adata.obs['is_correct'] = ct_adata.obs['Label_1'] == ct_adata.obs['predicted_labels']
    filtpred = ct_adata.obs[ct_adata.obs['conf_score'] > 0.5]
    match_counts = filtpred.groupby('Label_1')['is_correct'].sum()
    total_counts = filtpred['Label_1'].value_counts()
    result = pd.DataFrame({
        'total': total_counts,
        'correct_matches': match_counts
    })
    filtpred['is_correct'].sum()/filtpred.shape[0] # 0.9706400367526062
    result['accuracy'].median() # 0.9800539173117695
    result['accuracy'] = result['correct_matches'] / result['total']

    

# Execute 
if __name__ == '__main__':
    main()
    