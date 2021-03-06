from collections import OrderedDict
from functools import reduce
from typing import Dict, List, Optional, Callable
from warnings import warn
from torch.utils.data import Dataset
import csv
from PIL import Image
from pathlib import Path
import numpy as np


class CSVAnnotationDatasetWithUnderSampling(Dataset):
    def __init__(self, image_dir: str, annotation_dict: Dict[str, int], transforms,
                 label_dist: List[int], under_sampling_rate: List[float]):
        self._image_dir = image_dir
        self._annotation_dict = annotation_dict
        self._transforms = transforms
        self._n_classes = len(under_sampling_rate)
        self._filenames_by_classes = [[] for _ in range(self._n_classes)]
        for filename, label in self._annotation_dict.items():
            self._filenames_by_classes[label].append(filename)

        self._sampled_label_dist = list(map(lambda x_y: round(x_y[0] * x_y[1]), zip(under_sampling_rate, label_dist)))
        self._data_len = sum(self._sampled_label_dist)
        self._norm_label_dist = np.array(label_dist) / sum(label_dist)

    def __len__(self):
        return self._data_len

    def __getitem__(self, idx):
        label = np.random.choice([i for i in range(self._n_classes)], p=self._norm_label_dist)
        filenames = self._filenames_by_classes[label]
        filename = np.random.choice(filenames)
        label = self._annotation_dict[filename]
        filepath = Path(self._image_dir).joinpath(filename)
        img = Image.open(str(filepath))
        img = img.convert("RGB")
        if self._transforms:
            return self._transforms(img, label)
        return img, label

    def labels_distribution(self) -> List[int]:
        return self._sampled_label_dist


class CSVAnnotationDatasetWithOverSampling(Dataset):
    def __init__(self, image_dir: str, annotation_dict: Dict[str, int], transforms, over_sampling_rate: List[int]):
        self._image_dir = image_dir
        self._annotation_dict = annotation_dict
        self._transforms = transforms
        self._file_name_list = list(
            map(lambda filename_label: [filename_label[0]] * over_sampling_rate[filename_label[1]],
                annotation_dict.items()))  # Apply oversampling
        self._file_name_list = reduce(lambda a, b: a + b, self._file_name_list)  # Flatten list

    def __len__(self):
        return len(self._file_name_list)

    def __getitem__(self, idx):
        filename = self._file_name_list[idx]
        label = self._annotation_dict[filename]
        filepath = Path(self._image_dir).joinpath(filename)
        img = Image.open(str(filepath))
        img = img.convert("RGB")
        if self._transforms:
            return self._transforms(img, label)
        return img, label

    def labels_distribution(self, n_classes: int) -> List[int]:
        """
        summarize labels distribution.
        :return: result[label] = count
        """
        result = [0 for _ in range(n_classes)]
        for filename in self._file_name_list:
            result[self._annotation_dict[filename]] += 1
        return result


class CSVAnnotationDataset(Dataset):
    @staticmethod
    def create(image_dir: str, annotation_csv_filepath: str, transforms: Optional[Callable],
               label_dict: Dict[str, int] = None) -> 'CSVAnnotationDataset':
        """
        Create dataset from CSV file.
        If CSV column 2 value is string, required label_dict arg.
        :param label_dict:
        :param image_dir:
        :param annotation_csv_filepath: 
        :param transforms:
        :return:
        """
        filename_label_dict = CSVAnnotationDataset._create_filename_label_dict(annotation_csv_filepath, label_dict)
        return CSVAnnotationDataset(image_dir, filename_label_dict=filename_label_dict, transforms=transforms)

    @staticmethod
    def _create_filename_label_dict(annotation_csv_filepath: str, label_dict: Dict[str, int] = None) -> OrderedDict:
        filename_label_dict = OrderedDict()
        with open(annotation_csv_filepath, "r") as file:
            reader = csv.reader(file)
            for row in reader:
                filename = Path(row[0]).name
                label = row[1]
                if not label.isdigit():
                    if label_dict is None:
                        raise RuntimeError("Required dict transform label name to class number.")
                    label_num = label_dict.get(label)
                    if label_num is None:
                        warn(f"Invalid label name: {label},  {row}")
                        continue
                    filename_label_dict[filename] = label_num
                    continue
                filename_label_dict[filename] = int(label)
        return filename_label_dict

    def __init__(self, image_dir: str, filename_label_dict: OrderedDict, transforms: Optional[Callable]):
        self._image_dir = image_dir
        self._transforms = transforms
        self._filepath_label_dict = filename_label_dict

    def labels_distribution(self, n_classes: int) -> List[int]:
        """
        summarize labels distribution.
        :return: result[label] = count
        """
        result = [0 for _ in range(n_classes)]
        for label in self._filepath_label_dict.values():
            result[label] += 1
        return result

    def __len__(self):
        return len(self._filepath_label_dict)

    def __getitem__(self, idx):
        filename, label = list(self._filepath_label_dict.items())[idx]
        filepath = Path(self._image_dir).joinpath(filename)
        img = Image.open(str(filepath))
        img = img.convert("RGB")
        if self._transforms:
            return self._transforms(img, label)
        return img, label

    def split_dataset(self, indices: np.ndarray) -> 'CSVAnnotationDataset':
        new_annotation_dict_keys = list(
            filter(lambda index_key: index_key[0] in indices, enumerate(list(self._filepath_label_dict.keys()))))
        new_annotation_dict = OrderedDict()
        for _, key in new_annotation_dict_keys:
            new_annotation_dict[key] = self._filepath_label_dict[key]
        return CSVAnnotationDataset(self._image_dir, new_annotation_dict, self._transforms)

    def apply_over_sampling(self, over_sampling_rate: List[int]) -> CSVAnnotationDatasetWithOverSampling:
        return CSVAnnotationDatasetWithOverSampling(self._image_dir, self._filepath_label_dict,
                                                    self._transforms, over_sampling_rate)

    def apply_under_sampling(self, under_sampling_rate: List[float]) -> CSVAnnotationDatasetWithUnderSampling:
        return CSVAnnotationDatasetWithUnderSampling(self._image_dir, self._filepath_label_dict,
                                                     self._transforms,
                                                     self.labels_distribution(len(under_sampling_rate)),
                                                     under_sampling_rate)
