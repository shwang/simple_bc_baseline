import minerl
from sacred import Experiment
import basalt_utils.wrappers as wrapper_utils
from stable_baselines3.common.torch_layers import NatureCNN
from basalt_utils.sb3_compat.policies import SpaceFlatteningActorCriticPolicy
from basalt_utils.sb3_compat.cnns import MAGICALCNN
from stable_baselines3.common.policies import ActorCriticCnnPolicy
from imitation.algorithms.bc import BC
import torch as th
from basalt_utils import utils
import os
import imitation.util.logger as imitation_logger
from time import time

bc_baseline = Experiment("basalt_bc_baseline")

WRAPPERS = [# Transforms continuous camera action into discrete up/down/no-change buckets on both pitch and yaw
            wrapper_utils.CameraDiscretizationWrapper,
            # Flattens a Dict action space into a Box, but retains memory of how to expand back out
            wrapper_utils.ActionFlatteningWrapper,
            # Pull out only the POV observation from the observation space; transpose axes for SB3 compatibility
            utils.ExtractPOVAndTranspose] #,

            # Add a time limit to the environment (only relevant for testing)
            # utils.Testing10000StepLimitWrapper,
            # wrapper_utils.FrameSkip]

@bc_baseline.config
def default_config():
    task_name = "MineRLFindCaves-v0"
    train_batches = 10
    train_epochs = None
    log_interval = 1
    data_root = os.getenv('MINERL_DATA_ROOT', "/Users/cody/Code/il-representations/data/minecraft")
    # SpaceFlatteningActorCriticPolicy is a policy that supports a flattened Dict action space by
    # maintaining multiple sub-distributions and merging their results
    policy_class = SpaceFlatteningActorCriticPolicy
    wrappers = WRAPPERS
    save_location = "/Users/cody/Code/simple_bc_baseline/results"
    policy_path = 'trained_policy.pt'
    batch_size = 32
    n_traj = None
    lr = 1e-4
    _ = locals()
    del _

@bc_baseline.named_config
def normal_policy_class():
    policy_class = ActorCriticCnnPolicy
    _ = locals()
    del _


@bc_baseline.automain
def train_bc(task_name, batch_size, data_root, wrappers, train_epochs, n_traj, lr,
             policy_class, train_batches, log_interval, save_location, policy_path):

    # This code is designed to let you either train for a fixed number of batches, or for a fixed number of epochs
    assert train_epochs is None or train_batches is None, \
        "Only one of train_batches or train_epochs should be set"
    assert not (train_batches is None and train_epochs is None), \
        "You cannot have both train_epochs and train_epochs set to None"

    # This `get_data_pipeline_and_env` utility is designed to be shared across multiple baselines
    # It takes in a task name, data root, and set of wrappers and returns
    # (1) A "Dummy Env", i.e. an env with the same environment spaces as you'd getting from making the env associated
    #     with this task and wrapping it in `wrappers`, but without having to actually start up Minecraft
    # (2) A MineRL DataPipeline that can be used to construct a batch_iter used by BC, and also as a handle to clean
    #     up that iterator after training.
    data_pipeline, wrapped_dummy_env = utils.get_data_pipeline_and_env(task_name, data_root, wrappers)

    # This utility creates a data iterator that is basically a light wrapper around the baseline MineRL data iterator
    # that additionally:
    # (1) Applies all observation and action transformations specified by the wrappers in `wrappers`, and
    # (2) Calls `np.squeeze` recursively on all the nested dict spaces to remove the sequence dimension, since we're
    #     just doing single-frame BC here
    data_iter = utils.create_data_iterator(wrapped_dummy_env, data_pipeline, batch_size, train_epochs, n_traj)
    if policy_class == SpaceFlatteningActorCriticPolicy:
        policy = policy_class(observation_space=wrapped_dummy_env.observation_space,
                              action_space=wrapped_dummy_env.action_space,
                              env=wrapped_dummy_env,
                              lr_schedule=lambda _: 1e-4,
                              features_extractor_class=MAGICALCNN)
    else:
        policy = policy_class(observation_space=wrapped_dummy_env.observation_space,
                              action_space=wrapped_dummy_env.action_space,
                              lr_schedule=lambda _: 1e-4,
                              features_extractor_class=MAGICALCNN)

    run_save_location = os.path.join(save_location, str(round(time())))
    os.mkdir(run_save_location)
    imitation_logger.configure(run_save_location, ["stdout", "tensorboard"])
    bc_trainer = BC(
        observation_space=wrapped_dummy_env.observation_space,
        action_space=wrapped_dummy_env.action_space,
        policy_class= lambda **kwargs: policy,
        policy_kwargs=None,
        expert_data=data_iter,
        device='auto',
        optimizer_cls=th.optim.Adam,
        optimizer_kwargs=dict(lr=lr),
        ent_weight=1e-3,
        l2_weight=1e-5)
    bc_trainer.train(n_epochs=train_epochs,
                     n_batches=train_batches,
                     log_interval=log_interval)
    bc_trainer.save_policy(policy_path=os.path.join(run_save_location, policy_path))
    print("Training complete; cleaning up data pipeline!")
    data_pipeline.close()