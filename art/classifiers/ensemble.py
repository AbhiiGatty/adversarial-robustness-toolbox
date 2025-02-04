# MIT License
#
# Copyright (C) IBM Corporation 2018
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import numpy as np

from art.classifiers import Classifier

logger = logging.getLogger(__name__)


class EnsembleClassifier(Classifier):
    """
    Class allowing to aggregate multiple classifiers as an ensemble. The individual classifiers are expected to be
    trained when the ensemble is created and no training procedures are provided through this class.
    """
    def __init__(self, clip_values, classifiers, classifier_weights=None, channel_index=3, defences=None,
                 preprocessing=(0, 1)):
        """
        Initialize a :class:`EnsembleClassifier` object. The data range values and colour channel index have to
        be consistent for all the classifiers in the ensemble.

        :param clip_values: Tuple of the form `(min, max)` representing the minimum and maximum values allowed
               for features.
        :type clip_values: `tuple`
        :param classifiers: List of :class:`Classifier` instances to be ensembled together.
        :type classifiers: `list`
        :param classifier_weights: List of weights, one scalar per classifier, to assign to their prediction when
               aggregating results. If `None`, all classifiers are assigned the same weight.
        :type classifier_weights: `list` or `np.ndarray` or `None`
        :param channel_index: Index of the axis in data containing the color channels or features.
        :type channel_index: `int`
        :param defences: Defences to be activated with the classifier.
        :type defences: `str` or `list(str)`
        :param preprocessing: Tuple of the form `(substractor, divider)` of floats or `np.ndarray` of values to be
               used for data preprocessing. The first value will be substracted from the input. The input will then
               be divided by the second one.
        :type preprocessing: `tuple`
        """
        super(EnsembleClassifier, self).__init__(clip_values=clip_values, channel_index=channel_index,
                                                 defences=defences, preprocessing=preprocessing)

        if classifiers is None or not classifiers:
            raise ValueError('No classifiers provided for the ensemble.')
        self._nb_classifiers = len(classifiers)

        # Assert all classifiers are the right shape(s)
        for classifier in classifiers:
            if not isinstance(classifier, Classifier):
                raise TypeError('Expected type `Classifier`, found %s instead.' % type(classifier))

            if clip_values != classifier.clip_values:
                raise ValueError('Incompatible `clip_values` between classifiers in the ensemble. Found %s and %s.'
                                 % (str(clip_values), str(classifier.clip_values)))

            if classifier.nb_classes != classifiers[0].nb_classes:
                raise ValueError('Incompatible output shapes between classifiers in the ensemble. Found %s and %s.'
                                 % (str(classifier.nb_classes), str(classifiers[0].nb_classes)))

            if classifier.input_shape != classifiers[0].input_shape:
                raise ValueError('Incompatible input shapes between classifiers in the ensemble. Found %s and %s.'
                                 % (str(classifier.input_shape), str(classifiers[0].input_shape)))

        self._input_shape = classifiers[0].input_shape
        self._nb_classes = classifiers[0].nb_classes
        self._clip_values = clip_values

        # Set weights for classifiers
        if classifier_weights is None:
            classifier_weights = np.ones(self._nb_classifiers) / self._nb_classifiers
        self._classifier_weights = classifier_weights

        self._classifiers = classifiers

    def predict(self, x, logits=False, raw=False):
        """
        Perform prediction for a batch of inputs. Predictions from classifiers are aggregated at probabilities level,
        as logits are not comparable between models. If logits prediction was specified, probabilities are converted
        back to logits after aggregation.

        :param x: Test set.
        :type x: `np.ndarray`
        :param logits: `True` if the prediction should be done at the logits layer.
        :type logits: `bool`
        :param raw: Return the individual classifier raw outputs (not aggregated).
        :type raw: `bool`
        :return: Array of predictions of shape `(nb_inputs, self.nb_classes)`, or of shape
                 `(nb_classifiers, nb_inputs, self.nb_classes)` if `raw=True`.
        :rtype: `np.ndarray`
        """
        preds = np.array([self._classifier_weights[i] * self._classifiers[i].predict(x, raw and logits)
                          for i in range(self._nb_classifiers)])
        if raw:
            return preds

        # Aggregate predictions only at probabilities level, as logits are not comparable between models
        z = np.sum(preds, axis=0)

        # Convert back to logits if needed
        if logits:
            eps = 10e-8
            z = np.log(np.clip(z, eps, 1. - eps))
        return z

    def fit(self, x, y, batch_size=128, nb_epochs=20):
        """
        Fit the classifier on the training set `(x, y)`. This function is not supported for ensembles.

        :param x: Training data.
        :type x: `np.ndarray`
        :param y: Labels, one-vs-rest encoding.
        :type y: `np.ndarray`
        :param batch_size: Size of batches.
        :type batch_size: `int`
        :param nb_epochs: Number of epochs to use for trainings.
        :type nb_epochs: `int`
        :return: `None`
        """
        raise NotImplementedError

    def fit_generator(self, generator, nb_epochs=20):
        """
        Fit the classifier using the generator that yields batches as specified. This function is not supported for
        ensembles.

        :param generator: Batch generator providing `(x, y)` for each epoch. If the generator can be used for native
                          training in Keras, it will.
        :type generator: `DataGenerator`
        :param nb_epochs: Number of epochs to use for trainings.
        :type nb_epochs: `int`
        :return: `None`
        """
        raise NotImplementedError

    @property
    def layer_names(self):
        """
        Return the hidden layers in the model, if applicable. This function is not supported for ensembles.

        :return: The hidden layers in the model, input and output layers excluded.
        :rtype: `list`

        .. warning:: `layer_names` tries to infer the internal structure of the model.
                     This feature comes with no guarantees on the correctness of the result.
                     The intended order of the layers tries to match their order in the model, but this is not
                     guaranteed either.
        """
        raise NotImplementedError

    def get_activations(self, x, layer):
        """
        Return the output of the specified layer for input `x`. `layer` is specified by layer index (between 0 and
        `nb_layers - 1`) or by name. The number of layers can be determined by counting the results returned by
        calling `layer_names`. This function is not supported for ensembles.

        :param x: Input for computing the activations.
        :type x: `np.ndarray`
        :param layer: Layer for computing the activations
        :type layer: `int` or `str`
        :return: The output of `layer`, where the first dimension is the batch size corresponding to `x`.
        :rtype: `np.ndarray`
        """
        raise NotImplementedError

    def class_gradient(self, x, label=None, logits=False, raw=False):
        """
        Compute per-class derivatives w.r.t. `x`.

        :param x: Sample input with shape as expected by the model.
        :type x: `np.ndarray`
        :param label: Index of a specific per-class derivative. If `None`, then gradients for all
                      classes will be computed.
        :type label: `int`
        :param logits: `True` if the prediction should be done at the logits layer.
        :type logits: `bool`
        :param raw: Return the individual classifier raw outputs (not aggregated).
        :type raw: `bool`
        :return: Array of gradients of input features w.r.t. each class in the form
                 `(batch_size, nb_classes, input_shape)` when computing for all classes, otherwise shape becomes
                 `(batch_size, 1, input_shape)` when `label` parameter is specified. If `raw=True`, an additional
                 dimension is added at the beginning of the array, indexing the different classifiers.
        :rtype: `np.ndarray`
        """
        grads = np.array([self._classifier_weights[i] * self._classifiers[i].class_gradient(x, label, logits)
                          for i in range(self._nb_classifiers)])
        if raw:
            return grads
        return np.sum(grads, axis=0)

    def loss_gradient(self, x, y, raw=False):
        """
        Compute the gradient of the loss function w.r.t. `x`.

        :param x: Sample input with shape as expected by the model.
        :type x: `np.ndarray`
        :param y: Correct labels, one-vs-rest encoding.
        :type y: `np.ndarray`
        :param raw: Return the individual classifier raw outputs (not aggregated).
        :type raw: `bool`
        :return: Array of gradients of the same shape as `x`. If `raw=True`, shape becomes `[nb_classifiers, x.shape]`.
        :rtype: `np.ndarray`
        """
        grads = np.array([self._classifier_weights[i] * self._classifiers[i].loss_gradient(x, y)
                          for i in range(self._nb_classifiers)])
        if raw:
            return grads

        return np.sum(grads, axis=0)

    def set_learning_phase(self, train):
        """
        Set the learning phase for the backend framework.

        :param train: True to set the learning phase to training, False to set it to prediction.
        :type train: `bool`
        """
        if self._learning is not None and isinstance(train, bool):
            for classifier in self._classifiers:
                classifier.set_learning_phase(train)
            self._learning_phase = train

    def save(self, filename, path=None):
        """
        Save a model to file in the format specific to the backend framework. This function is not supported for
        ensembles.

        :param filename: Name of the file where to store the model.
        :type filename: `str`
        :param path: Path of the folder where to store the model. If no path is specified, the model will be stored in
                     the default data location of the library `DATA_PATH`.
        :type path: `str`
        :return: None
        """
        raise NotImplementedError
