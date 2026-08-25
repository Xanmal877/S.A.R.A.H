from enum import Enum, auto
from typing import Any, Dict, List, Optional

class PartiesEnum(Enum):
    LEADER = auto()
    MEMBERS = auto()
    SETTINGS = auto()

class PartySettingEnum(Enum):
    XP_MODE = auto()
    XP_SHARE_RANGE = auto()
    LEADER_PERCENTAGE = auto()
    MEMBER_PERCENTAGE = auto()

class XpModeEnum(Enum):
    EQUAL = auto()
    PERCENTAGE = auto()

class PartyModule:
    current_global_party_id: int = -1
    parties: Dict[int, Dict] = {}

    def __init__(self, owner_soul=None):
        self.soul = owner_soul
        self.party_id = -1
        self.current_party: Dict = {}
        self.party_loot_turns: Dict[int, int] = {}
        self.party_being_created: bool = False

    def startup(self):
        self.sync_data(True)
        self.current_party = self.find_party(self.party_id)

    def sync_data(self, from_soul: bool = False):
        if not self.soul:
            return
        if from_soul:
            from .soul import SoulModulesEnum
            self.current_party = self.soul.soulModuleDicts.get(SoulModulesEnum.PARTY, {}).copy()
            return
        
        from .soul import SoulModulesEnum
        self.soul.soulModuleDicts[SoulModulesEnum.PARTY] = self.current_party.copy()

    def create_party(self) -> int:
        if self.party_being_created:
            return -1

        self.party_being_created = True
        self.party_id = self.get_next_party_id()

        PartyModule.parties[self.party_id] = {
            PartiesEnum.LEADER: self.soul,
            PartiesEnum.MEMBERS: [self.soul],
            PartiesEnum.SETTINGS: {
                PartySettingEnum.XP_MODE: XpModeEnum.EQUAL,
                PartySettingEnum.XP_SHARE_RANGE: 150.0,
                PartySettingEnum.LEADER_PERCENTAGE: 0.5,
                PartySettingEnum.MEMBER_PERCENTAGE: 0.5,
            }
        }

        self.current_party = PartyModule.parties[self.party_id].copy()
        self.party_loot_turns[self.party_id] = 0
        self.party_being_created = False
        return self.party_id

    def join_party(self, party_id: int) -> bool:
        if party_id not in PartyModule.parties:
            return False

        self.party_id = party_id
        self.current_party = PartyModule.parties[party_id]
        members = self.current_party[PartiesEnum.MEMBERS]
        
        if self.soul not in members:
            members.append(self.soul)
        return True

    def leave_party(self):
        if self.party_id not in PartyModule.parties:
            return

        members = self.current_party[PartiesEnum.MEMBERS]
        if self.soul in members:
            members.remove(self.soul)

        if len(members) == 0:
            self.disband_party()
        elif self.current_party[PartiesEnum.LEADER] == self.soul and len(members) > 0:
            self.current_party[PartiesEnum.LEADER] = members[0]

        self.party_id = -1

    def disband_party(self):
        if self.party_id in PartyModule.parties:
            del PartyModule.parties[self.party_id]
        if self.party_id in self.party_loot_turns:
            del self.party_loot_turns[self.party_id]

    def find_party(self, party_id: int) -> Dict:
        return PartyModule.parties.get(party_id, {})

    def get_next_party_id(self) -> int:
        PartyModule.current_global_party_id += 1
        return PartyModule.current_global_party_id
