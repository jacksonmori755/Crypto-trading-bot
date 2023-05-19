import logging
from typing import Dict, List, Tuple

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from pandas import DataFrame
from torch.nn import functional as F

from freqtrade.exceptions import OperationalException
from freqtrade.freqai.base_models.BasePyTorchModel import BasePyTorchModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen


logger = logging.getLogger(__name__)


class BasePyTorchClassifier(BasePyTorchModel):
    """
    A PyTorch implementation of a classifier.
    User must implement fit method

    Important!

    - User must declare the target class names in the strategy,
    under IStrategy.set_freqai_targets method.

    for example, in your strategy:
    ```
        def set_freqai_targets(self, dataframe: DataFrame, metadata: Dict, **kwargs):
            self.freqai.class_names = ["down", "up"]
            dataframe['&s-up_or_down'] = np.where(dataframe["close"].shift(-100) >
                                                  dataframe["close"], 'up', 'down')

            return dataframe
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.class_name_to_index = None
        self.index_to_class_name = None

    def predict(
        self, unfiltered_df: DataFrame, dk: FreqaiDataKitchen, **kwargs
    ) -> Tuple[DataFrame, npt.NDArray[np.int_]]:
        """
        Filter the prediction features data and predict with it.
        :param dk: dk: The datakitchen object
        :param unfiltered_df: Full dataframe for the current backtest period.
        :return:
        :pred_df: dataframe containing the predictions
        :do_predict: np.array of 1s and 0s to indicate places where freqai needed to remove
        data (NaNs) or felt uncertain about data (PCA and DI index)
        :raises ValueError: if 'class_names' doesn't exist in model meta_data.
        """

        class_names = self.model.model_meta_data.get("class_names", None)
        if not class_names:
            raise ValueError(
                "Missing class names. "
                "self.model.model_meta_data['class_names'] is None."
            )

        if not self.class_name_to_index:
            self.init_class_names_to_index_mapping(class_names)

        dk.find_features(unfiltered_df)
        filtered_df, _ = dk.filter_features(
            unfiltered_df, dk.training_features_list, training_filter=False
        )
        filtered_df = dk.normalize_data_from_metadata(filtered_df)
        dk.data_dictionary["prediction_features"] = filtered_df
        self.data_cleaning_predict(dk)
        x = self.data_convertor.convert_x(
            dk.data_dictionary["prediction_features"],
            device=self.device
        )
        self.model.model.eval()
        logits = self.model.model(x)
        probs = F.softmax(logits, dim=-1)
        predicted_classes = torch.argmax(probs, dim=-1)
        predicted_classes_str = self.decode_class_names(predicted_classes)
        # used .tolist to convert probs into an iterable, in this way Tensors
        # are automatically moved to the CPU first if necessary.
        pred_df_prob = DataFrame(probs.detach().tolist(), columns=class_names)
        pred_df = DataFrame(predicted_classes_str, columns=[dk.label_list[0]])
        pred_df = pd.concat([pred_df, pred_df_prob], axis=1)
        return (pred_df, dk.do_predict)

    def encode_class_names(
            self,
            data_dictionary: Dict[str, pd.DataFrame],
            dk: FreqaiDataKitchen,
            class_names: List[str],
    ):
        """
        encode class name, str -> int
        assuming first column of *_labels data frame to be the target column
        containing the class names
        """

        target_column_name = dk.label_list[0]
        for split in self.splits:
            label_df = data_dictionary[f"{split}_labels"]
            self.assert_valid_class_names(label_df[target_column_name], class_names)
            label_df[target_column_name] = list(
                map(lambda x: self.class_name_to_index[x], label_df[target_column_name])
            )

    @staticmethod
    def assert_valid_class_names(
            target_column: pd.Series,
            class_names: List[str]
    ):
        non_defined_labels = set(target_column) - set(class_names)
        if len(non_defined_labels) != 0:
            raise OperationalException(
                f"Found non defined labels: {non_defined_labels}, ",
                f"expecting labels: {class_names}"
            )

    def decode_class_names(self, class_ints: torch.Tensor) -> List[str]:
        """
        decode class name, int -> str
        """

        return list(map(lambda x: self.index_to_class_name[x.item()], class_ints))

    def init_class_names_to_index_mapping(self, class_names):
        self.class_name_to_index = {s: i for i, s in enumerate(class_names)}
        self.index_to_class_name = {i: s for i, s in enumerate(class_names)}
        logger.info(f"encoded class name to index: {self.class_name_to_index}")

    def convert_label_column_to_int(
            self,
            data_dictionary: Dict[str, pd.DataFrame],
            dk: FreqaiDataKitchen,
            class_names: List[str]
    ):
        self.init_class_names_to_index_mapping(class_names)
        self.encode_class_names(data_dictionary, dk, class_names)

    def get_class_names(self) -> List[str]:
        if not self.class_names:
            raise ValueError(
                "self.class_names is empty, "
                "set self.freqai.class_names = ['class a', 'class b', 'class c'] "
                "inside IStrategy.set_freqai_targets method."
            )

        return self.class_names
