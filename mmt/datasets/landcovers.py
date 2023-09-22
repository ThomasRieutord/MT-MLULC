#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multiple land-cover/land-use Maps Translation (MMT)

Global land cover maps
"""
import os
import numpy as np
import rasterio
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import torchgeo.datasets as tgd
from typing import Any, Dict, Optional

from mmt import _repopath_ as mmt_repopath
from mmt.utils import config as utilconf

config = utilconf.get_config_from_yaml(
    os.path.join(mmt_repopath, "configs", "new_config_template.yaml")
)

ecoclimapsg_labels = """0. no data
1. sea and oceans
2. lakes
3. rivers
4. bare land
5. bare rock
6. permanent snow
7. boreal broadleaf deciduous
8. temperate broadleaf deciduous
9. tropical broadleaf deciduous
10. temperate broadleaf evergreen
11. tropical broadleaf evergreen
12. boreal needleleaf evergreen
13. temperate needleleaf evergreen
14. boreal needleleaf deciduous
15. shrubs
16. boreal grassland
17. temperate grassland
18. tropical grassland
19. winter C3 crops
20. summer C3 crops
21. C4 crops
22. flooded trees
23. flooded grassland
24. LCZ1: compact high-rise
25. LCZ2: compact midrise
26. LCZ3: compact low-rise
27. LCZ4: open high-rise
28. LCZ5: open midrise
29: LCZ6: open low-rise
30: LCZ7: lightweight low-rise
31: LCZ8: large low-rise
32: LCZ9: sparsely built
33: LCZ10: heavy industry""".split("\n")

n_ecoclimapsg_labels = len(ecoclimapsg_labels)


ecoclimapsg_label_hierarchy = {
    "water":[
        "1. sea and oceans",
        "2. lakes",
        "3. rivers",
    ],
    "bareland":[
        "4. bare land",
        "5. bare rock",
    ],
    "snow":[
        "6. permanent snow",
    ],
    "trees":[
        "7. boreal broadleaf deciduous",
        "8. temperate broadleaf deciduous",
        "9. tropical broadleaf deciduous",
        "10. temperate broadleaf evergreen",
        "11. tropical broadleaf evergreen",
        "12. boreal needleleaf evergreen",
        "13. temperate needleleaf evergreen",
        "14. boreal needleleaf deciduous",
    ],
    "shrubs":[
        "15. shrubs",
    ],
    "grassland":[
        "16. boreal grassland",
        "17. temperate grassland",
        "18. tropical grassland",
    ],
    "crops":[
        "19. winter C3 crops",
        "20. summer C3 crops",
        "21. C4 crops",
    ],
    "flooded_veg":[
        "22. flooded trees",
        "23. flooded grassland",
    ],
    "urban":[
        "24. LCZ1: compact high-rise",
        "25. LCZ2: compact midrise",
        "26. LCZ3: compact low-rise",
        "27. LCZ4: open high-rise",
        "28. LCZ5: open midrise",
        "29: LCZ6: open low-rise",
        "30: LCZ7: lightweight low-rise",
        "31: LCZ8: large low-rise",
        "32: LCZ9: sparsely built",
        "33: LCZ10: heavy industry",
    ],
}


def parse_version_infos(path):
    """Read all the fields from the file version-info.txt"""
    version_file = os.path.join(path, "version-infos.txt")
    assert os.path.isfile(version_file), f"Missing version file. Please create file {version_file}'"
    infos = {}
    with open(version_file, "r") as f:
        for l in f.readlines():
            k, v = l.split("=")
            infos[k] = v.split('"')[1]
        
    return infos

class TorchgeoLandcover(tgd.RasterDataset):
    """Abstract class for land cover dataset using TorchGeo.
    
    This class is a [customised TorchGeo RasterDataset](https://torchgeo.readthedocs.io/en/latest/tutorials/custom_raster_dataset.html).
    The customisation is in the precision of the path where to find the data and several
    attributes that are common to all land covers classes.
    
    
    Parameters
    ----------
    transforms: Optional[Callable[[dict[str, Any]], dict[str, Any]]]
        A function/transform that takes an input sample and returns a transformed version
    
    
    Main attributes
    ---------------
    path: str
        Absolute path to the root directory containing the data
        
    filename_glob: str
        Glob expression used to search for files

    is_image: bool=False
        True if dataset contains imagery, False if dataset contains mask

    separate_files: bool=False
        True if data is stored in a separate file for each band, else False.
    
    crs: `rasterio.crs.CRS`
        Coordinate reference system in which the land cover is
    
    labels: list of str
        Labels names
    
    cmap: list of 3-tuple
        Colormap for each 
    
    
    Main methods
    ------------
    __getitem__: Return a sample of data
    plot: Plot a sample of data
    """
    path = ""
    filename_glob = "*.tif"
    is_image = False
    separate_files = False
    crs = None
    labels = []
    cmap = []
    
    def __init__(self, crs = None, res = None, transforms = None, tgeo_init = True):
        self.n_labels = len(self.labels)
        if tgeo_init:
            super().__init__(self.path, crs = crs, res = res, transforms = transforms)
        
    def plot(
        self,
        sample: Dict[str, Any],
        show_titles: bool = True,
        suptitle: Optional[str] = None,
        figax = None
    ):
        """Plot a sample of data.


        Parameters
        ----------
        sample: dict
            Sample of data. Labels must be accessible under the 'mask' key.

        show_titles: bool, default=True
            True if a title is diplayed over the figure.

        suptitle: str
            If provided, the string given here is put as main title of the figure.
        """
        assert len(self.labels) == len(self.cmap), f"The number of labels ({len(self.labels)}) do not match the number of colors ({len(self.cmap)})"
        
        cmap = ListedColormap(np.array(self.cmap)/255)
        if figax is None:
            fig, ax = plt.subplots(1, 1)
        else:
            fig, ax = figax
        
        label = sample["mask"].squeeze()
        ul = np.unique(label).astype(int)
        nx, ny = label.shape
        im = ax.imshow(label, cmap=cmap, vmin=0, vmax=len(self.labels)-1)
        if show_titles:
            ax.set_title(self.__class__.__name__)
        if len(ul) > 2:
            cbar = plt.colorbar(im, values=ul, spacing="uniform", shrink=0.5, ticks=ul)
            cbar.ax.set_yticklabels([self.labels[i] for i in ul])
        else:
            for i, l in enumerate(ul):
                ax.text(int(nx/3), int(ny/3) + i * int(ny/4), self.labels[l])

        if suptitle is not None:
            plt.suptitle(suptitle)
        
        return fig, ax


class EcoclimapSG(TorchgeoLandcover):
    path = os.path.join(config.paths.data_dir, "tiff_data", "ECOCLIMAP-SG")
    filename_glob = "ECOCLIMAP-SG-Eurat.tif"
    labels = ecoclimapsg_labels
    cmap = [
        (0,0,0),(0,0,128),(0,0,205),(0, 0, 255),(211,211,211),(169,169,169),(255,250,250),
        (240,255,240),(85,107,47),(154,205,50),(0,128,0),(255,127,80),(160,82,45),(34,139,34),
        (188,143,143),(205,133,63),(222,184,135),(50,205,50),(255,215,0),(32,178,170),(173,255,47),
        (189,183,107),(102,102,0),(46,139,87),(138,2,0),(206,0,0),(252,1,1),(255,90,0),(255,120,0),
        (255,150,0),(255,180,0),(255,210,0),(255,240,0),(128,128,128)
    ]
    crs = rasterio.crs.CRS.from_epsg(4326)


class ESAWorldCover(TorchgeoLandcover):
    path = os.path.join(config.paths.data_dir, "tiff_data", "ESA-WorldCover-2021")#, "ESA_WorldCover_10m_2021_v200_60deg_macrotile_N30E000")
    labels = [
        "Tree cover", "Shrubland", "Grassland", "Cropland", "Built-up",
        "Bare/sparse veg.", "Snow and ice", "Permanent water bodies",
        "Herbaceous wetland", "Mangroves", "Moss and lichen"
    ]
    cmap = [
        (0,100,0), (255, 187, 34), (255, 255, 76), (240, 150, 255), (250, 0, 0), (180, 180, 180),
        (240, 240, 240), (0, 100, 200), (0, 150, 160), (0, 207, 117), (250, 230, 160)
    ]
    crs = rasterio.crs.CRS.from_epsg(4326)


class EcoclimapSGplus(TorchgeoLandcover):
    path = os.path.join(config.paths.data_dir, "tiff_data", "ECOCLIMAP-SG-plus", f"ecosgp-labels-v{config.versions.ecosgplus}")
    labels = ecoclimapsg_labels
    cmap = [
        (0,0,0),(0,0,128),(0,0,205),(0, 0, 255),(211,211,211),(169,169,169),(255,250,250),
        (240,255,240),(85,107,47),(154,205,50),(0,128,0),(255,127,80),(160,82,45),(34,139,34),
        (188,143,143),(205,133,63),(222,184,135),(50,205,50),(255,215,0),(32,178,170),(173,255,47),
        (189,183,107),(102,102,0),(46,139,87),(138,2,0),(206,0,0),(252,1,1),(255,90,0),(255,120,0),
        (255,150,0),(255,180,0),(255,210,0),(255,240,0),(128,128,128)
    ]
    crs = rasterio.crs.CRS.from_string(parse_version_infos(path)["crs"])
    
    def get_version(self):
        """Read the version from the file version-info.txt"""
        version_file = os.path.join(self.path, "version-infos.txt")
        assert os.path.isfile(version_file), f"Missing version file. Please create file {version_file} with a line 'version=xxx'"
        with open(version_file, "r") as f:
            for l in f.readlines():
                if "version=" in l:
                    return l.split('"')[1]


class QualityFlagsECOSGplus(EcoclimapSGplus):
    path = os.path.join(config.paths.data_dir, "tiff_data", "ECOCLIMAP-SG-plus", f"ecosgp-qflags-v{config.versions.ecosgplus}")
    labels = [
        "0. no data",
        "1. high agreement score + ECOSG",
        "2. high agreement score",
        "3. low agreement score + ECOSG",
        "4. low agreement score", 
        "5. no mode match + ECOSG",
        "6. no mode match"
    ]
    cmap = [(0, 0, 0), (134, 218, 134), (60, 182, 60), (255, 191, 191), (255, 127, 127), (255, 64, 64), (255, 0, 0)]
    