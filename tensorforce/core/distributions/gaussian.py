# Copyright 2018 Tensorforce Team. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from math import e, log, pi

import tensorflow as tf

from tensorforce import util
from tensorforce.core import layer_modules
from tensorforce.core.distributions import Distribution


class Gaussian(Distribution):
    """
    Gaussian distribution, for unbounded continuous actions.
    """

    def __init__(self, name, action_spec, embedding_size):
        """
        Categorical distribution.
        """
        super().__init__(name=name, action_spec=action_spec, embedding_size=embedding_size)

        action_size = util.product(xs=self.action_spec['shape'], empty=0)
        input_spec = dict(type='float', shape=(embedding_size,))
        self.mean = self.add_module(
            name='mean', module='linear', modules=layer_modules, size=action_size,
            input_spec=input_spec
        )
        self.log_stddev = self.add_module(
            name='log-stddev', module='linear', modules=layer_modules, size=action_size,
            input_spec=input_spec
        )

    def tf_parameterize(self, x):
        # Flat mean and log standard deviation
        mean = self.mean.apply(x=x)
        log_stddev = self.log_stddev.apply(x=x)

        # Reshape mean and log stddev to action shape
        shape = (-1,) + self.action_spec['shape']
        mean = tf.reshape(tensor=mean, shape=shape)
        log_stddev = tf.reshape(tensor=log_stddev, shape=shape)

        # Clip log stddev for numerical stability
        log_eps = log(util.epsilon)  # epsilon < 1.0, hence negative
        log_stddev = tf.clip_by_value(
            t=log_stddev, clip_value_min=log_eps, clip_value_max=-log_eps
        )

        # Standard deviation
        stddev = tf.exp(x=log_stddev)

        mean, log_stddev = self.add_summary(
            label='distribution', name='mean', tensor=mean, pass_tensors=(mean, log_stddev)
        )
        stddev, log_stddev = self.add_summary(
            label='distribution', name='stddev', tensor=stddev, pass_tensors=(stddev, log_stddev)
        )

        return mean, stddev, log_stddev

    def state_value(self, distr_params):
        _, _, log_stddev = distr_params
        return -log_stddev - 0.5 * log(2.0 * pi)

    def state_action_value(self, distr_params, action):
        mean, stddev, log_stddev = distr_params
        sq_mean_distance = tf.square(x=(action - mean))
        sq_stddev = tf.maximum(x=tf.square(x=stddev), y=util.epsilon)
        return -0.5 * sq_mean_distance / sq_stddev - 2.0 * log_stddev - log(2.0 * pi)

    def tf_sample(self, distr_params, deterministic):
        mean, stddev, _ = distr_params

        # Deterministic: mean as action
        definite = mean

        # Non-deterministic: sample action using default normal distribution
        normal_distribution = tf.random_normal(shape=tf.shape(input=mean))
        sampled = mean + stddev * normal_distribution

        return tf.where(condition=deterministic, x=definite, y=sampled)

    def tf_log_probability(self, distr_params, action):
        mean, stddev, log_stddev = distr_params
        sq_mean_distance = tf.square(x=(action - mean))
        sq_stddev = tf.maximum(x=tf.square(x=stddev), y=util.epsilon)
        return -0.5 * sq_mean_distance / sq_stddev - log_stddev - 0.5 * log(2.0 * pi)

    def tf_entropy(self, distr_params):
        _, _, log_stddev = distr_params
        return log_stddev + 0.5 * log(2.0 * pi * e)

    def tf_kl_divergence(self, distr_params1, distr_params2):
        mean1, stddev1, log_stddev1 = distr_params1
        mean2, stddev2, log_stddev2 = distr_params2

        log_stddev_ratio = log_stddev2 - log_stddev1
        sq_mean_distance = tf.square(x=(mean1 - mean2))
        sq_stddev1 = tf.square(x=stddev1)
        sq_stddev2 = tf.maximum(x=tf.square(x=stddev2), y=util.epsilon)

        return log_stddev_ratio + 0.5 * (sq_stddev1 + sq_mean_distance) / sq_stddev2 - 0.5

    def tf_regularization_loss(self):
        regularization_loss = super().tf_regularization_loss()
        if regularization_loss is None:
            losses = list()
        else:
            losses = [regularization_loss]

        regularization_loss = self.mean.regularization_loss()
        if regularization_loss is not None:
            losses.append(regularization_loss)

        regularization_loss = self.log_stddev.regularization_loss()
        if regularization_loss is not None:
            losses.append(regularization_loss)

        if len(losses) > 0:
            return tf.add_n(inputs=losses)
        else:
            return None
