"""Plot the mean disclosure profile of each cluster."""

from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from src.part2.common import THEMES


def plot_profiles(profiles, labels, output_path):
    """Display relative theme weights rather than document text shares."""
    profiles, labels = np.asarray(profiles), np.asarray(labels)
    clusters = np.unique(labels)
    counts = [int(np.sum(labels == cluster)) for cluster in clusters]
    names = [f'C{cluster} (n={count})' for cluster, count in zip(clusters, counts)]
    means = np.array([profiles[labels == cluster].mean(axis=0) for cluster in clusters])
    with plt.rc_context({'font.size': 9, 'axes.linewidth': .6}):
        fig, heatmap = plt.subplots(figsize=(9, 3.5), layout='constrained')
        image = heatmap.imshow(means, cmap='Greys', vmin=0, vmax=1, aspect='auto')
        heatmap.set(yticks=range(len(clusters)),
                    yticklabels=names, xticks=range(len(THEMES)),
                    xticklabels=list(THEMES))
        heatmap.tick_params(axis='both', length=0)
        plt.setp(heatmap.get_xticklabels(), rotation=35, ha='right')
        fig.colorbar(image, ax=heatmap, label='Mean normalized weight',
                     fraction=.025, pad=.025, ticks=[0, .5, 1])
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, metadata={'Software': 'Matplotlib'})
        plt.close(fig)
