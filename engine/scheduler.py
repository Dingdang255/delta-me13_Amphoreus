"""L4：调度器。

它只关心【有没有违例、违例码是什么】，不关心是哪个位。
死循环不在这里 —— 它不是任何一条恢复策略，而是【没有策略可受理】的后果：
policies.json 里没有 VACANT，decide() 找不到对应条目，便落回 CONTINUE，
世界只能就那么继续演化下去（结构冻结由此自然产生，而非被配置出来）。
"""
from __future__ import annotations


class Action:
    __slots__ = ("kind", "terminates", "codes")

    def __init__(self, kind, terminates=False, codes=()):
        self.kind = kind
        self.terminates = terminates
        self.codes = tuple(codes)

    def next_state(self, x, snapshot):
        if self.kind == "REPLAY":
            return snapshot          # 帧初快照：世界原地重放
        return x


PRIORITY = ("VACANT", "OVERFLOW", "UNCONSERVED", "UNSOLVED")


def _advanced(st, snapshot) -> bool:
    """本帧是否发生了结构性推进。只看通用计数器，不看是哪个位、哪个人。"""
    return (st.promotions != snapshot.promotions
            or st.round != snapshot.round
            or st.domain_index != snapshot.domain_index
            or st.world_clock != snapshot.world_clock)


class Scheduler:
    def decide(self, st, violations, ctx, frame, snapshot=None):
        codes = {v.code for v in violations}

        # 噪声【本底】：每帧恒定注入一丝乱码。量取自旧机制 —— 旧世界里 CapacityCheck 恒真、
        # OVERFLOW 常驻，`policies.OVERFLOW.noise_rate` 被每帧加一次（`code not in codes` 从不
        # 拦它），世界稳定在 noise_rate/(1−noise_decay) = 0.085/0.12 = 0.7083 —— plot / nullify /
        # tide 的实测噪声都建立在这个恒定注入上。判据改成【份额口径】后 OVERFLOW 变稀疏，那口
        # 恒定注入会断掉 ⇒ 噪声会自熄、tide 也少掉这一档，故显式补回。**条件与旧注入逐条对齐**：
        # 旧注入在 PRIORITY 循环里，而 PRIORITY 最前是 VACANT、会抢先 `return`（不注入）——
        # 故等价的触发条件正是「VACANT ∉ codes」；其余帧（含一条违例都没有的帧）一律注入。
        # 于是安静帧与旧世界逐位一致，只有真溢出帧（另加 OVERFLOW 的 noise_rate 尖峰）才偏离。
        # 量见 config/params.json 的 noise_base。
        if "VACANT" not in codes:
            st.noise += float(ctx.params.get("noise_base", 0.0))

        if not codes:
            return Action("STEP", codes=())

        for code in PRIORITY:
            if code not in codes:
                continue
            pol = ctx.policy(code)
            strategy = pol.get("strategy", "CONTINUE")

            if strategy == "REPLAY_SAME_FRAME":
                # 原地重放 = 这一帧确实【原地踏步】。若本帧发生了结构性推进
                # （再创世 / 显式域推进 / 世界钟前进），它就不是一次忠实重放。
                # 判据与【哪个位】无关，只看通用计数器。
                if snapshot is not None and _advanced(st, snapshot):
                    return Action("STEP", codes=codes)
                st.add_score("replayed_frames")
                return Action("REPLAY", codes=codes)

            if strategy == "EMIT_VISUAL_NOISE":
                # 溢出当帧把噪声【抬到一个上限值】（取 max，**不累加**）。累加语义下，连续溢出
                # 的世界会把噪声推到 `base + rate/(1−noise_decay) = 0.71 + 2.67 = 3.38`，越过
                # 本该只属 tide 的 `tau_noise_annihilation`(3.0) ⇒ 既有世界短暂闯进「淹没」模式。
                # 取 max 后：安静帧仍是【本底】（与旧世界逐位一致）、溢出帧抬到 `noise_peak`
                # （越过 `tau_noise_parley`）、且**永不累积** ⇒ 正常世界的噪声上界就是 noise_peak，
                # 只有 tide（噪声 5.1，另有 raise_noise 驱动）才真的淹过 3.0。配置见 policies.json。
                st.noise = max(st.noise, float(pol.get("noise_peak", 0.0)))
                st.add_score("black_tide")
                return Action("STEP", codes=codes)

            if strategy == "ADVANCE_DOMAIN":
                st.add_score("unsolved_frames")
                return Action("STEP", codes=codes)

            return Action("STEP", codes=codes)
        return Action("STEP", codes=codes)