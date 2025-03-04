import gym
from .reversible_action_wrapper import ReversibleActionWrapper
import numpy as np

class AnssiActionShaping(ReversibleActionWrapper):
    def __init__(self, env, camera_angle=10, always_attack=False):
        super().__init__(env)

        self.camera_angle = camera_angle
        self.always_attack = always_attack
        self._actions = [
            [('attack', 1)],
            [('forward', 1)],
            [('forward', 1), ('jump', 1)],
            [('camera', [-self.camera_angle, 0])],
            [('camera', [self.camera_angle, 0])],
            [('camera', [0, self.camera_angle])],
            [('camera', [0, -self.camera_angle])],
        ]

        self.actions = []
        for actions in self._actions:
            act = self.env.action_space.noop()
            for a, v in actions:
                act[a] = v
            if self.always_attack:
                act['attack'] = 1
            self.actions.append(act)

        self.action_space = gym.spaces.Discrete(len(self.actions))

    def action(self, action):
        return self.actions[action]

    def reverse_action(self, action):
        camera_actions = action["camera"].squeeze()
        attack_actions = action["attack"].squeeze()
        forward_actions = action["forward"].squeeze()
        jump_actions = action["jump"].squeeze()
        batch_size = len(camera_actions)
        actions = np.zeros((batch_size,), dtype=np.int)

        for i in range(len(camera_actions)):
            # Moving camera is most important (horizontal first)
            if camera_actions[i][0] < -self.camera_angle:
                actions[i] = 3
            elif camera_actions[i][0] > self.camera_angle:
                actions[i] = 4
            elif camera_actions[i][1] > self.camera_angle:
                actions[i] = 5
            elif camera_actions[i][1] < -self.camera_angle:
                actions[i] = 6
            elif forward_actions[i] == 1:
                if jump_actions[i] == 1:
                    actions[i] = 2
                else:
                    actions[i] = 1
            elif attack_actions[i] == 1:
                actions[i] = 0
            else:
                # No reasonable mapping (would be no-op)
                actions[i] = -1

        return actions