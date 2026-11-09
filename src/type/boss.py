
class Boss:
    def __init__(self, name: str, id_num: int):
        self._name = name
        self.id_num = id_num

    def name(self) -> str:
        return self._name
