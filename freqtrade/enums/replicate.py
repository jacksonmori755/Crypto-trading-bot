from enum import Enum


class ReplicateModeType(str, Enum):
    leader = "leader"
    follower = "follower"


class LeaderMessageType(str, Enum):
    whitelist = "whitelist"
