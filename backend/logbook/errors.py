"""存储层与业务代码共享的异常，屏蔽具体驱动。"""


class StorageError(Exception):
    """存储层异常基类。"""


class WriteRejected(StorageError):
    """单条语句被数据库拒绝（类型、约束等），可用于标记导入失败。"""


class UniqueConflict(WriteRejected):
    """唯一约束冲突，用于返回 409。"""


class StorageUnavailable(StorageError):
    """连接中断或数据库暂不可用，可重试。"""
