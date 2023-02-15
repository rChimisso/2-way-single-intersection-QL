from typing import Callable
from stable_baselines3.dqn.dqn import DQN
import os
import sys
if 'SUMO_HOME' in os.environ:
  tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
  sys.path.append(tools)
else:
  sys.exit("Please declare the environment variable 'SUMO_HOME'")
from sumo_rl import SumoEnvironment
import traci

def execution(updateMetrics: Callable[[str, dict[str, float]], None], name: str, seconds: int, fixed: bool):
  env = SumoEnvironment(
    net_file='nets/2way-single-intersection/single-intersection.net.xml',
    route_file='nets/2way-single-intersection/single-intersection-vhvh.rou.xml',
    out_csv_name='outputs/2way-single-intersection/dqn',
    single_agent=True,
    use_gui=False,
    num_seconds=seconds,
    fixed_ts=fixed
  )
  model = DQN(
    env=env,
    policy="MlpPolicy",
    learning_rate=0.001,
    learning_starts=0,
    train_freq=1,
    target_update_interval=500,
    exploration_initial_eps=0.05,
    exploration_final_eps=0.01,
    verbose=1
  )
  model.learn(total_timesteps=seconds, callback=lambda locals, _: updateMetrics(name, locals['infos'][0]))