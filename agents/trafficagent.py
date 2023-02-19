import os
import sys
from datetime import datetime
from typing import Union, Callable
from abc import ABC, abstractmethod
from utils.plotter import Plotter, Metric
from stable_baselines3.dqn.dqn import DQN
if 'SUMO_HOME' in os.environ:
  tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
  sys.path.append(tools)
else:
  sys.exit("Please declare the environment variable 'SUMO_HOME'")
from sumo_rl import SumoEnvironment
from sumo_rl.agents import QLAgent
from sumo_rl.exploration import EpsilonGreedy

class TrafficAgent(ABC):
  def __init__(
    self,
    name: str,
    color: str,
    fixed_ts: bool,
    single_agent: bool,
    net_file: str,
    route_file: str,
    num_seconds: int,
    delta_time: int,
    yellow_time: int,
    min_green: int,
    max_green: int,
  ) -> None:
    self.name = name
    self.color = color
    self.fixed_ts = fixed_ts
    self.single_agent = single_agent
    self.net_file = net_file
    self.route_file = route_file
    self.num_seconds = num_seconds
    self.delta_time = delta_time
    self.yellow_time = yellow_time
    self.min_green = min_green
    self.max_green = max_green
    self.plotter = Plotter(color, ['system_total_stopped', 'system_total_waiting_time', 'system_mean_waiting_time', 'system_mean_speed', 't_stopped', 't_accumulated_waiting_time', 't_average_speed', 'agents_total_stopped', 'agents_total_accumulated_waiting_time'], x_lim = num_seconds)

  def _get_csv_name(self, *args: tuple[str, Union[int, float]]) -> str:
    experiment_time = str(datetime.now()).split('.')[0].replace(':', '-')
    experiment_parameters = ','.join([f'{arg[0]}={arg[1]}' for arg in args])
    return f'outputs/{self.name}/{experiment_time},{experiment_parameters}'

  def _get_env(
    self,
    out_csv_name: str,
    use_gui: bool,
    add_system_info: bool,
    add_per_agent_info: bool
  ) -> SumoEnvironment:
    return SumoEnvironment(
      net_file = self.net_file,
      route_file = self.route_file,
      out_csv_name = out_csv_name,
      use_gui = use_gui,
      num_seconds = self.num_seconds,
      delta_time = self.delta_time,
      yellow_time = self.yellow_time,
      min_green = self.min_green,
      max_green = self.max_green,
      add_system_info = add_system_info,
      add_per_agent_info = add_per_agent_info,
      fixed_ts = self.fixed_ts,
      single_agent = self.single_agent
    )
  
  @abstractmethod
  def _get_agent(self, env: SumoEnvironment):
    raise NotImplementedError()

  def _update_metrics(self, info: dict[Metric, float], callback: Callable[[float, Metric, str], None]) -> None:
    for metric in info:
      self.plotter.append(info[metric], metric)
      callback(info[metric], metric, self.name)

  @abstractmethod
  def _learn(self, env: SumoEnvironment, agent, update_metrics: Callable[[dict[Metric, float]], None]) -> None:
    raise NotImplementedError()
  
  @abstractmethod
  def _save_model(self):
    raise NotImplementedError()

  def _save_csv(self, env: SumoEnvironment) -> None:
    env.save_csv(env.out_csv_name, 0)

  def _save_plots(self) -> None:
    self.plotter.save(self.name)

  def learn(
    self,
    update_metrics: Callable[[float, Metric, str], None],
    add_system_info: bool = True,
    add_per_agent_info: bool = True,
    use_gui: bool = False
  ) -> None:
    env = self._get_env(
      self._get_csv_name(
        ('num_seconds', self.num_seconds),
        ('delta_time', self.delta_time),
        ('yellow_time', self.yellow_time),
        ('min_green', self.min_green),
        ('max_green', self.max_green)
      ),
      use_gui,
      add_system_info,
      add_per_agent_info
    )
    self._learn(env, self._get_agent(env), lambda info: self._update_metrics(info, update_metrics))
    self._save_model()
    self._save_csv(env)
    self._save_plots()
    env.close()

class FixedCycleTrafficAgent(TrafficAgent):
  def __init__(
    self,
    name: str,
    color: str,
    net_file: str,
    route_file: str,
    num_seconds: int,
    delta_time: int,
    yellow_time: int,
    min_green: int,
    max_green: int
  ) -> None:
    super().__init__(name, color, True, False, net_file, route_file, num_seconds - delta_time, delta_time, yellow_time, min_green, max_green)

  def _get_agent(self, _: SumoEnvironment) -> None:
    return None

  def _learn(self, env: SumoEnvironment, _: None, update_metrics: Callable[[dict[Metric, float]], None]):
    env.reset()
    done: dict[str, bool] = {'__all__': False}
    while not done['__all__']:
      _, _, done, _ = env.step({}) # type: ignore
      update_metrics(env.metrics[-1])

  def _save_model(self):
    pass

class QLearningTrafficAgent(TrafficAgent):
  def __init__(
    self,
    name: str,
    color: str,
    net_file: str,
    route_file: str,
    num_seconds: int,
    delta_time: int,
    yellow_time: int,
    min_green: int,
    max_green: int,
    alpha: float = 0.1,
    gamma: float = 0.99,
    initial_epsilon: float = 1,
    min_epsilon: float = 0.005
  ) -> None:
    super().__init__(name, color, False, False, net_file, route_file, num_seconds - delta_time, delta_time, yellow_time, min_green, max_green)
    self.alpha = alpha
    self.gamma = gamma
    self.initial_epsilon = initial_epsilon
    self.min_epsilon = min_epsilon

  def _get_agent(self, env: SumoEnvironment) -> dict[str, QLAgent]:
    initial_states = env.reset()
    ql_agents = {
      ts: QLAgent(
        starting_state = env.encode(initial_states[ts], ts),
        state_space = env.observation_space,
        action_space = env.action_space,
        alpha = self.alpha,
        gamma = self.gamma,
        exploration_strategy = EpsilonGreedy(
          initial_epsilon = self.initial_epsilon,
          min_epsilon = self.min_epsilon,
          decay = 0.9
        )
      ) for ts in env.ts_ids
    }
    return ql_agents

  def _learn(self, env: SumoEnvironment, agent: dict[str, QLAgent], update_metrics: Callable[[dict[Metric, float]], None]):
    done: dict[str, bool] = {'__all__': False}
    while not done['__all__']:
      actions = {ts: agent[ts].act() for ts in agent.keys()}
      state, reward, done, _ = env.step(action = actions) # type: ignore
      update_metrics(env.metrics[-1])
      for agent_id in agent.keys():
        agent[agent_id].learn(next_state = env.encode(state[agent_id], agent_id), reward = reward[agent_id]) # type: ignore

  def _save_model(self):
    pass

class DeepQLearningTrafficAgent(TrafficAgent):
  def __init__(
    self,
    name: str,
    color: str,
    net_file: str,
    route_file: str,
    num_seconds: int,
    delta_time: int,
    yellow_time: int,
    min_green: int,
    max_green: int,
    alpha: float = 0.1,
    gamma: float = 0.99,
    initial_epsilon: float = 1,
    min_epsilon: float = 0.005
  ) -> None:
    super().__init__(name, color, False, True, net_file, route_file, num_seconds // delta_time, delta_time, yellow_time, min_green, max_green)
    self.alpha = alpha
    self.gamma = gamma
    self.initial_epsilon = initial_epsilon
    self.min_epsilon = min_epsilon

  def _get_agent(self, env: SumoEnvironment) -> DQN:
    return DQN(
      policy = "MlpPolicy",
      env = env,
      learning_rate = self.alpha,
      learning_starts = 0,
      gamma = self.gamma,
      train_freq = 1,
      gradient_steps = 1,
      target_update_interval = 500,
      exploration_fraction = 0.1,
      exploration_initial_eps = self.initial_epsilon,
      exploration_final_eps = self.min_epsilon,
      verbose = 1
    )

  def _learn(self, _: SumoEnvironment, agent: DQN, update_metrics: Callable[[dict[Metric, float]], None]):
    agent.learn(total_timesteps = self.num_seconds, callback = lambda locals, _: update_metrics(locals['infos'][0]))

  def _save_model(self):
    pass
