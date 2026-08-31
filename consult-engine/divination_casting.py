"""起卦适配层(运行态):随机性只住在这里(INV-01 边界)。

确定性引擎(liuyao/meihua)只接受完整输入、不含任何随机/时钟依赖;
系统起卦在此生成并连同来源标记一起交给引擎与存档(可回放)。
"""

from __future__ import annotations

import secrets


def system_cast_liuyao() -> dict:
    """电子摇卦:三枚硬币×六次(背记3、字记2),密码学随机,逐爻记录,标注系统起卦。"""
    lines = [sum(3 if secrets.randbelow(2) else 2 for _ in range(3)) for _ in range(6)]
    return {"method": "system_random", "lines": lines}


def manual_cast_liuyao(lines: list[int]) -> dict:
    """手动摇卦录入:原样透传,标注手动来源;合法性由确定性引擎校验。"""
    return {"method": "manual_coins", "lines": list(lines)}
