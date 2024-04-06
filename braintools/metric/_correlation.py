# Copyright 2024 BrainPy Ecosystem Limited. All Rights Reserved.
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

# -*- coding: utf-8 -*-

from typing import Union

import braincore as bc
import numpy as onp
from jax import vmap, lax, numpy as jnp

__all__ = [
  'cross_correlation',
  'voltage_fluctuation',
  'matrix_correlation',
  'weighted_correlation',
  'functional_connectivity',
  'functional_connectivity_dynamics',
]


def cross_correlation(spikes: bc.typing.ArrayLike,
                      bin: Union[int, float],
                      dt: Union[int, float] =None,
                      method: str = 'loop'):
  r"""Calculate cross correlation index between neurons.

  The coherence [1]_ between two neurons i and j is measured by their
  cross-correlation of spike trains at zero time lag within a time bin
  of :math:`\Delta t = \tau`. More specifically, suppose that a long
  time interval T is divided into small bins of :math:`\Delta t` and
  that two spike trains are given by :math:`X(l)=` 0 or 1, :math:`Y(l)=` 0
  or 1, :math:`l=1,2, \ldots, K(T / K=\tau)`. Thus, we define a coherence
  measure for the pair as:

  .. math::

      \kappa_{i j}(\tau)=\frac{\sum_{l=1}^{K} X(l) Y(l)}
      {\sqrt{\sum_{l=1}^{K} X(l) \sum_{l=1}^{K} Y(l)}}

  The population coherence measure :math:`\kappa(\tau)` is defined by the
  average of :math:`\kappa_{i j}(\tau)` over many pairs of neurons in the
  network.

  .. note::
     To JIT compile this function, users should make ``bin``, ``dt``, ``numpy`` static.
     For example, ``partial(brainpy.measure.cross_correlation, bin=10, numpy=False)``.

  Parameters
  ----------
  spikes : ndarray
      The history of spike states of the neuron group.
  bin : float, int
      The time bin to normalize spike states.
  dt : float, optional
      The time precision.
  method: str
    The method to calculate all pairs of cross correlation.
    Supports two kinds of methods: `loop` and `vmap`.
    `vmap` method needs much more memory.

  Returns
  -------
  cc_index : float
      The cross correlation value which represents the synchronization index.

  References
  ----------
  .. [1] Wang, Xiao-Jing, and György Buzsáki. "Gamma oscillation by synaptic
         inhibition in a hippocampal interneuronal network model." Journal of
         neuroscience 16.20 (1996): 6402-6413.
  """
  dt = bc.environ.get_dt() if dt is None else dt
  bin_size = int(bin / dt)
  num_hist, num_neu = spikes.shape
  num_bin = int(onp.ceil(num_hist / bin_size))
  if num_bin * bin_size != num_hist:
    spikes = jnp.append(spikes, jnp.zeros((num_bin * bin_size - num_hist, num_neu)), axis=0)
  states = spikes.T.reshape((num_neu, num_bin, bin_size))
  states = jnp.asarray(jnp.sum(states, axis=2) > 0., dtype=jnp.float_)
  indices = jnp.tril_indices(num_neu, k=-1)

  if method == 'loop':
    def _f(i, j):
      sqrt_ij = jnp.sqrt(jnp.sum(states[i]) * jnp.sum(states[j]))
      return lax.cond(sqrt_ij == 0.,
                      lambda _: 0.,
                      lambda _: jnp.sum(states[i] * states[j]) / sqrt_ij,
                      None)

    res = bc.transform.for_loop(_f, *indices)

  elif method == 'vmap':
    @vmap
    def _cc(i, j):
      sqrt_ij = jnp.sqrt(jnp.sum(states[i]) * jnp.sum(states[j]))
      return lax.cond(sqrt_ij == 0.,
                      lambda _: 0.,
                      lambda _: jnp.sum(states[i] * states[j]) / sqrt_ij,
                      None)

    res = _cc(*indices)
  else:
    raise ValueError(f'Do not support {method}. We only support "loop" or "vmap".')

  return jnp.mean(jnp.asarray(res))


def _f_signal(signal):
  return jnp.mean(signal * signal) - jnp.mean(signal) ** 2


def voltage_fluctuation(potentials, method='loop'):
  r"""Calculate neuronal synchronization via voltage variance.

  The method comes from [1]_ [2]_ [3]_.

  First, average over the membrane potential :math:`V`

  .. math::

      V(t) = \frac{1}{N} \sum_{i=1}^{N} V_i(t)

  The variance of the time fluctuations of :math:`V(t)` is

  .. math::

      \sigma_V^2 = \left\langle \left[ V(t) \right]^2 \right\rangle_t -
      \left[ \left\langle V(t) \right\rangle_t \right]^2

  where :math:`\left\langle \ldots \right\rangle_t = (1 / T_m) \int_0^{T_m} dt \, \ldots`
  denotes time-averaging over a large time, :math:`\tau_m`. After normalization
  of :math:`\sigma_V` to the average over the population of the single cell
  membrane potentials

  .. math::

      \sigma_{V_i}^2 = \left\langle\left[ V_i(t) \right]^2 \right\rangle_t -
      \left[ \left\langle V_i(t) \right\rangle_t \right]^2

  one defines a synchrony measure, :math:`\chi (N)`, for the activity of a system
  of :math:`N` neurons by:

  .. math::

      \chi^2 \left( N \right) = \frac{\sigma_V^2}{ \frac{1}{N} \sum_{i=1}^N
      \sigma_{V_i}^2}

  .. [1] Golomb, D. and Rinzel J. (1993) Dynamics of globally coupled
         inhibitory neurons with heterogeneity. Phys. Rev. E 48:4810-4814.
  .. [2] Golomb D. and Rinzel J. (1994) Clustering in globally coupled
         inhibitory neurons. Physica D 72:259-282.
  .. [3] David Golomb (2007) Neuronal synchrony measures. Scholarpedia, 2(1):1347.

  Args:
    potentials: The membrane potential matrix of the neuron group.
    method: The method to calculate all pairs of cross correlation.
       Supports two kinds of methods: `loop` and `vmap`.
      `vmap` method will consume much more memory.

  Returns:
    sync_index: The synchronization index.
  """

  avg = jnp.mean(potentials, axis=1)
  avg_var = jnp.mean(avg * avg) - jnp.mean(avg) ** 2

  if method == 'loop':
    _var = bc.transform.for_loop(_f_signal, jnp.moveaxis(potentials, 0, 1))
  elif method == 'vmap':
    _var = vmap(_f_signal, in_axes=1)(potentials)
  else:
    raise ValueError(f'Do not support {method}. We only support "loop" or "vmap".')
  
  var_mean = jnp.mean(_var)
  r = jnp.where(var_mean == 0., 1., avg_var / var_mean)
  return r


def matrix_correlation(x, y):
  """Pearson correlation of the lower triagonal of two matrices.

    The triangular matrix is offset by k = 1 in order to ignore the diagonal line

  Parameters
  ----------
  x: ndarray
    First matrix.
  y: ndarray
    Second matrix
  numpy: bool
    Whether we use numpy array as the functional output.
    If ``False``, this function can be JIT compiled.

  Returns
  -------
  coef: ndarray
    Correlation coefficient
  """
  if x.ndim != 2:
    raise ValueError(f'Only support 2d array, but we got a array '
                     f'with the shape of {x.shape}')
  if y.ndim != 2:
    raise ValueError(f'Only support 2d array, but we got a array '
                     f'with the shape of {y.shape}')
  x = x[jnp.triu_indices_from(x, k=1)]
  y = y[jnp.triu_indices_from(y, k=1)]
  cc = jnp.corrcoef(x, y)[0, 1]
  return cc


def functional_connectivity(activities):
  """Functional connectivity matrix of timeseries activities.

  Parameters
  ----------
  activities: ndarray
    The multidimensional array with the shape of ``(num_time, num_sample)``.
  numpy: bool
    Whether we use numpy array as the functional output.
    If ``False``, this function can be JIT compiled.

  Returns
  -------
  connectivity_matrix: ndarray
    ``num_sample x num_sample`` functional connectivity matrix.
  """
  if activities.ndim != 2:
    raise ValueError('Only support 2d array with shape of "(num_time, num_sample)". '
                     f'But we got a array with the shape of {activities.shape}')
  fc = jnp.corrcoef(activities.T)
  return jnp.nan_to_num(fc)


def functional_connectivity_dynamics(activities, window_size=30, step_size=5):
  """Computes functional connectivity dynamics (FCD) matrix.

  Parameters
  ----------
  activities: ndarray
    The time series with shape of ``(num_time, num_sample)``.
  window_size: int
    Size of each rolling window in time steps, defaults to 30.
  step_size: int
    Step size between each rolling window, defaults to 5.

  Returns
  -------
  fcd_matrix: ndarray
    FCD matrix.
  """
  pass


def weighted_correlation(x, y, w):
  """Weighted Pearson correlation of two data series.

  Parameters
  ----------
  x: ndarray
    The data series 1.
  y: ndarray
    The data series 2.
  w: ndarray
    Weight vector, must have same length as x and y.

  Returns
  -------
  corr: ndarray
    Weighted correlation coefficient.
  """

  def _weighted_mean(x, w):
    """Weighted Mean"""
    return jnp.sum(x * w) / jnp.sum(w)

  def _weighted_cov(x, y, w):
    """Weighted Covariance"""
    return jnp.sum(w * (x - _weighted_mean(x, w)) * (y - _weighted_mean(y, w))) / jnp.sum(w)

  if x.ndim != 1:
    raise ValueError(f'Only support 1d array, but we got a array '
                     f'with the shape of {x.shape}')
  if y.ndim != 1:
    raise ValueError(f'Only support 1d array, but we got a array '
                     f'with the shape of {y.shape}')
  if w.ndim != 1:
    raise ValueError(f'Only support 1d array, but we got a array '
                     f'with the shape of {w.shape}')
  return _weighted_cov(x, y, w) / jnp.sqrt(_weighted_cov(x, x, w) * _weighted_cov(y, y, w))
