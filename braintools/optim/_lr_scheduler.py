# Copyright 2024 BDP Ecosystem Limited. All Rights Reserved.
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

from typing import Sequence, Union

import numpy as np
import braincore as bc
import jax
import jax.numpy as jnp

__all__ = [
  'LearningRateScheduler',
  'ConstantLR',
  'StepLR',
  'MultiStepLR',
  'CosineAnnealingLR',
  'CosineAnnealingWarmRestarts',
  'ExponentialLR',
  'ExponentialDecayLR',
  'InverseTimeDecayLR',
  'PolynomialDecayLR',
  'PiecewiseConstantLR',
]


# learning rate schedules #
# ----------------------- #


def make_schedule(scalar_or_schedule):
  if isinstance(scalar_or_schedule, LearningRateScheduler):
    return scalar_or_schedule
  elif isinstance(scalar_or_schedule, (int, float, bc.State)):
    return ConstantLR(scalar_or_schedule)
  else:
    raise TypeError(type(scalar_or_schedule))


class LearningRateScheduler(bc.Module):
  """
  The learning rate scheduler.

  Attributes
  ----------
  lr: float, State
    The learning rate.
  last_epoch: int
    The index of last epoch.

  """

  def __init__(self, lr: Union[float, bc.State], last_epoch: int = -1):
    super(LearningRateScheduler, self).__init__()
    if isinstance(lr, bc.State):
      lr.value = jnp.asarray(lr.value, dtype=bc.environ.dftype())
    else:
      lr = jnp.asarray(lr, dtype=bc.environ.dftype())
    self._lr = lr
    assert last_epoch >= -1, 'last_epoch should be greater than -1.'
    self.last_epoch = bc.State(jnp.asarray(last_epoch, dtype=bc.environ.ditype()))

  @property
  def lr(self):
    return self._lr.value if isinstance(self._lr, bc.State) else self._lr

  @lr.setter
  def lr(self, value):
    if isinstance(value, bc.State):
      value = value.value
    assert jnp.ndim(value) == 0, 'The learning rate should be a scalar.'
    if isinstance(self._lr, bc.State):
      self._lr.value = value
    else:
      self._lr = value

  def step_epoch(self):
    """
    Update the epoch count.
    """
    self.last_epoch.value += 1

  def step_call(self):
    """
    Update the call count.
    """
    pass

  def __repr__(self):
    return f'{self.__class__.__name__}(lr={self.lr.value}, last_epoch={self.last_epoch.value}{self.extra_repr()})'

  def extra_repr(self):
    return ''

  def __call__(self, i=None):
    raise NotImplementedError


class ConstantLR(LearningRateScheduler):
  """
  Constant learning rate scheduler.
  """

  def __call__(self, i=None):
    return self.lr


class CallBasedLRScheduler(LearningRateScheduler):
  """
  The learning rate scheduler based on the call count.

  Attributes
  ----------
  lr: float
    The learning rate.
  last_epoch: int
    The index of last epoch.
  last_call: int
    The index of last call.

  """

  def __init__(self, lr: Union[float, bc.State], last_epoch: int = -1, last_call: int = -1):
    super().__init__(lr=lr, last_epoch=last_epoch)

    assert last_call >= -1, 'last_call should be greater than -1.'
    self.last_call = bc.State(jnp.asarray(last_call, dtype=bc.environ.ditype()))

  def step_call(self):
    """
    Update the call count.
    """
    self.last_call.value += 1

  def __repr__(self):
    return (f'{self.__class__.__name__}(lr={self.lr.value}, '
            f'last_epoch={self.last_epoch.value}, '
            f'last_call={self.last_call.value}{self.extra_repr()})')


class StepLR(LearningRateScheduler):
  """Decays the learning rate of each parameter group by gamma every
  `step_size` epochs.

  Parameters
  ----------
  lr: float
    Initial learning rate.
  step_size: int
    Period of learning rate decay.
  gamma: float
    Multiplicative factor of learning rate decay.
    Default: 0.1.
  last_epoch: int
    The index of last epoch. Default: -1.
  """

  def __init__(
      self,
      lr: float,
      step_size: int,
      gamma: float = 0.1,
      last_epoch: int = -1
  ):
    super().__init__(lr=lr, last_epoch=last_epoch)

    assert step_size >= 1, 'step_size should be greater than or equal to 1.'
    assert 1. >= gamma >= 0, 'gamma should be in the range [0, 1].'
    self.step_size = step_size
    self.gamma = gamma

  def __call__(self, i=None):
    i = (self.last_epoch.value + 1) if i is None else i
    return self.lr * self.gamma ** (jnp.floor_divide(i, self.step_size))

  def extra_repr(self):
    return f', gamma={self.gamma}, step_size={self.step_size}'


class MultiStepLR(LearningRateScheduler):
  """Decays the learning rate of each parameter group by gamma once the
  number of epoch reaches one of the milestones. Notice that such decay can
  happen simultaneously with other changes to the learning rate from outside
  this scheduler. When last_epoch=-1, sets initial lr as lr.

  Parameters
  ----------
  lr: float
    Initial learning rate.
  milestones: sequence of int
    List of epoch indices. Must be increasing.
  gamma: float
    Multiplicative factor of learning rate decay.
    Default: 0.1.
  last_epoch: int
    The index of last epoch. Default: -1.
  """

  def __init__(
      self,
      lr: float,
      milestones: Sequence[int],
      gamma: float = 0.1,
      last_epoch: int = -1
  ):
    super().__init__(lr=lr, last_epoch=last_epoch)

    assert len(milestones) > 0, 'milestones should be a non-empty sequence.'
    assert all([milestones[i] < milestones[i + 1] for i in range(len(milestones) - 1)]), (
      'milestones should be a sequence of increasing integers.'
    )
    assert 1. >= gamma >= 0, 'gamma should be in the range [0, 1].'
    self.milestones = jnp.asarray((-1,) + tuple(milestones) + (np.iinfo(np.int32).max,), dtype=bc.environ.ditype())
    self.gamma = gamma

  def __call__(self, i=None):
    i = (self.last_epoch.value + 1) if i is None else i
    conditions = jnp.logical_and((i >= self.milestones[:-1]), (i < self.milestones[1:]))
    p = jnp.argmax(conditions)
    return self.lr * self.gamma ** p

  def extra_repr(self):
    return f', milestones={self.milestones}, gamma={self.gamma}'


class CosineAnnealingLR(LearningRateScheduler):
  r"""Set the learning rate of each parameter group using a cosine annealing
  schedule, where :math:`\eta_{max}` is set to the initial lr and
  :math:`T_{cur}` is the number of epochs since the last restart in SGDR:

  .. math::
      \begin{aligned}
          \eta_t & = \eta_{min} + \frac{1}{2}(\eta_{max} - \eta_{min})\left(1
          + \cos\left(\frac{T_{cur}}{T_{max}}\pi\right)\right),
          & T_{cur} \neq (2k+1)T_{max}; \\
          \eta_{t+1} & = \eta_{t} + \frac{1}{2}(\eta_{max} - \eta_{min})
          \left(1 - \cos\left(\frac{1}{T_{max}}\pi\right)\right),
          & T_{cur} = (2k+1)T_{max}.
      \end{aligned}

  When last_epoch=-1, sets initial lr as lr. Notice that because the schedule
  is defined recursively, the learning rate can be simultaneously modified
  outside this scheduler by other operators. If the learning rate is set
  solely by this scheduler, the learning rate at each step becomes:

  .. math::
      \eta_t = \eta_{min} + \frac{1}{2}(\eta_{max} - \eta_{min})\left(1 +
      \cos\left(\frac{T_{cur}}{T_{max}}\pi\right)\right)

  It has been proposed in
  `SGDR: Stochastic Gradient Descent with Warm Restarts`_. Note that this only
  implements the cosine annealing part of SGDR, and not the restarts.

  Parameters
  ----------
  lr: float
    Initial learning rate.
  T_max: int
    Maximum number of iterations.
  eta_min: float
    Minimum learning rate. Default: 0.
  last_epoch: int
    The index of last epoch. Default: -1.

  .. _SGDR\: Stochastic Gradient Descent with Warm Restarts:
      https://arxiv.org/abs/1608.03983
  """

  def __init__(
      self,
      lr: float,
      T_max: int,
      eta_min: float = 0.,
      last_epoch: int = -1,
  ):
    super().__init__(lr=lr, last_epoch=last_epoch)

    assert T_max >= 1, 'T_max should be greater than or equal to 1.'
    self._init_epoch = last_epoch
    self.T_max = T_max
    self.eta_min = eta_min

  def __call__(self, i=None):
    i = (self.last_epoch.value + 1) if i is None else i
    return self.eta_min + (self.lr - self.eta_min) * (1 + jnp.cos(jnp.pi * i / self.T_max)) / 2

  def extra_repr(self):
    return f', T_max={self.T_max}, eta_min={self.eta_min}'


class CosineAnnealingWarmRestarts(CallBasedLRScheduler):
  """Set the learning rate of each parameter group using a cosine annealing
  schedule, where :math:`\eta_{max}` is set to the initial lr, :math:`T_{cur}`
  is the number of epochs since the last restart and :math:`T_{i}` is the number
  of epochs between two warm restarts in SGDR:

  .. math::
      \eta_t = \eta_{min} + \frac{1}{2}(\eta_{max} - \eta_{min})\left(1 +
      \cos\left(\frac{T_{cur}}{T_{i}}\pi\right)\right)

  When :math:`T_{cur}=T_{i}`, set :math:`\eta_t = \eta_{min}`.
  When :math:`T_{cur}=0` after restart, set :math:`\eta_t=\eta_{max}`.

  It has been proposed in
  `SGDR: Stochastic Gradient Descent with Warm Restarts`_.

  Parameters
  ----------
  lr: float
    Initial learning rate.
  num_call_per_epoch: int
    The number the scheduler to call in each epoch.
    This usually means the number of batch in each epoch training.
  T_0: int
    Number of iterations for the first restart.
  T_mult: int
    A factor increases :math:`T_{i}` after a restart. Default: 1.
  eta_min: float
    Minimum learning rate. Default: 0.
  last_call: int
    The index of last call. Default: -1.

  .. _SGDR\: Stochastic Gradient Descent with Warm Restarts:
      https://arxiv.org/abs/1608.03983
  """

  def __init__(
      self,
      lr: float,
      num_call_per_epoch: int,
      T_0: int,
      T_mult: int = 1,
      eta_min: float = 0.,
      last_epoch: int = -1,
      last_call: int = -1
  ):
    super().__init__(lr=lr, last_call=last_call, last_epoch=last_epoch)
    if T_0 <= 0 or not isinstance(T_0, int):
      raise ValueError("Expected positive integer T_0, but got {}".format(T_0))
    if T_mult < 1 or not isinstance(T_mult, int):
      raise ValueError("Expected integer T_mult >= 1, but got {}".format(T_mult))

    self.T_mult = T_mult
    self.eta_min = eta_min
    self.T_0 = T_0
    self.num_call_per_epoch = num_call_per_epoch

  def _cond1(self, epoch):
    if self.T_mult == 1:
      T_cur = epoch % self.T_0
      T_i = self.T_0
    else:
      n = jnp.floor(jnp.log(epoch / self.T_0 * (self.T_mult - 1) + 1) / jnp.log(self.T_mult))
      T_cur = epoch - self.T_0 * (self.T_mult ** n - 1) / (self.T_mult - 1)
      T_i = self.T_0 * self.T_mult ** n
    return T_cur, T_i

  def _cond2(self, epoch):
    return epoch, self.T_0

  def __call__(self, i=None):
    epoch = self.current_epoch(i)
    T_cur, T_i = jax.lax.cond(epoch >= self.T_0, self._cond1, self._cond2, epoch)
    return self.eta_min + (self.lr - self.eta_min) * (1 + jnp.cos(jnp.pi * T_cur / T_i)) / 2

  def current_epoch(self, i=None):
    i = (self.last_call.value + 1) if i is None else i
    return jnp.floor(i / self.num_call_per_epoch)

  def extra_repr(self):
    return f', T_0={self.T_0}, T_mult={self.T_mult}, eta_min={self.eta_min}'


class ExponentialLR(LearningRateScheduler):
  """Decays the learning rate of each parameter group by gamma every epoch.
  When last_epoch=-1, sets initial lr as lr.

  Parameters
  ----------
  lr: float
    Initial learning rate.
  gamma: float
    Multiplicative factor of learning rate decay.
  last_epoch: int
    The index of last epoch. Default: -1.
  """

  def __init__(self,
               lr: float,
               gamma: float,
               last_epoch: int = -1):
    super(ExponentialLR, self).__init__(lr=lr, last_epoch=last_epoch)
    assert 1. >= gamma >= 0, 'gamma should be in the range [0, 1].'
    self.gamma = gamma

  def __call__(self, i: int = None):
    i = (self.last_epoch.value + 1) if i is None else i
    return self.lr * self.gamma ** i

  def extra_repr(self):
    return f', gamma={self.gamma}'


class ExponentialDecayLR(CallBasedLRScheduler):
  def __init__(self, lr, decay_steps, decay_rate, last_epoch: int = -1, last_call: int = -1):
    super().__init__(lr=lr, last_epoch=last_epoch, last_call=last_call)
    self.decay_steps = decay_steps
    self.decay_rate = decay_rate

  def __call__(self, i=None):
    i = (self.last_call.value + 1) if i is None else i
    return self.lr * self.decay_rate ** (i / self.decay_steps)

  def extra_repr(self):
    return f', decay_steps={self.decay_steps}, decay_rate={self.decay_rate}'


class InverseTimeDecayLR(ExponentialDecayLR):
  def __init__(self, lr, decay_steps, decay_rate, staircase=False,
               last_epoch: int = -1, last_call: int = -1):
    super().__init__(lr, decay_steps, decay_rate, last_epoch=last_epoch, last_call=last_call)
    self.staircase = staircase

  def __call__(self, i=None):
    i = (self.last_call.value + 1) if i is None else i
    if self.staircase:
      return self.lr / (1 + self.decay_rate * jnp.floor(i / self.decay_steps))
    else:
      return self.lr / (1 + self.decay_rate * i / self.decay_steps)

  def extra_repr(self):
    return f', decay_steps={self.decay_steps}, decay_rate={self.decay_rate}, staircase={self.staircase}'


class PolynomialDecayLR(CallBasedLRScheduler):
  def __init__(self, lr, decay_steps, final_lr, power=1.0, last_epoch: int = -1, last_call: int = -1):
    super(PolynomialDecayLR, self).__init__(lr, last_epoch=last_epoch, last_call=last_call)
    self.decay_steps = decay_steps
    self.final_lr = final_lr
    self.power = power

  def __call__(self, i=None):
    i = (self.last_call.value + 1) if i is None else i
    i = jnp.minimum(i, self.decay_steps)
    step_mult = (1 - i / self.decay_steps) ** self.power
    return step_mult * (self.lr - self.final_lr) + self.final_lr

  def extra_repr(self):
    return f', decay_steps={self.decay_steps}, final_lr={self.final_lr}, power={self.power}'


class PiecewiseConstantLR(CallBasedLRScheduler):
  def __init__(self, boundaries, values, last_epoch: int = -1, last_call: int = -1):
    super().__init__(0., last_epoch=last_epoch, last_call=last_call)

    boundaries = jnp.array(boundaries)
    values = jnp.array(values)
    if not boundaries.ndim == values.ndim == 1:
      raise ValueError("boundaries and values must be sequences")
    if not boundaries.shape[0] == values.shape[0] - 1:
      raise ValueError("boundaries length must be one shorter than values length")
    self.boundaries = boundaries
    self.values = values

  def __call__(self, i=None):
    i = (self.last_call.value + 1) if i is None else i
    return self.values[jnp.sum(i > self.boundaries)]

  def extra_repr(self):
    return f', boundaries={self.boundaries}, values={self.values}'
