import random
import polars as pl

from mobox.utils.decorators import valid_return
from mobox.utils.scenario import parse_scenario_from_pb


class WaymoScenarioGenerator:
    def __init__(self, cfg):
        self.cfg = cfg
        meta_file = cfg.DATA.META_FILE
        df_meta = pl.read_csv(meta_file)
        df_meta = df_meta.filter((pl.col("is_vru") == 0) &
                                 (pl.col("track_orient").is_in(["STRAIGHT", "STRAIGHT_LEFT", "STRAIGHT_RIGHT", "LEFT_TURN", "RIGHT_TURN"])) &
                                 (pl.col("track_length").is_in(["SHORT", "MEDIUM", "LONG"])) &
                                 (pl.col("dist_to_ego") > 0) &
                                 (pl.col("dist_to_ego") < 80))
        df_meta = df_meta[:500]
        self.N = len(df_meta)
        self.df_meta = df_meta
        self.meta = df_meta.partition_by("track_orient", as_dict=True)
        self.keys = list(self.meta.keys())

    @property
    def scenarios(self):
        for i in range(self.N):
            pb_file = self.meta[i, "scenario_file"]
            scenario = parse_scenario_from_pb(pb_file)
            yield scenario

    @valid_return
    def get(self, balance=False):
        if balance:
            key = random.choice(self.keys)
            row = self.meta[key].sample()
        else:
            idx = random.randrange(self.N)
            row = self.df_meta[idx]
        pb_file = row[0, "scenario_file"]
        track_id = row[0, "track_id"]
        scenario = parse_scenario_from_pb(pb_file)
        if scenario:
            return scenario, track_id
        return None

    def __len__(self):
        return 10000


if __name__ == "__main__":
    from config.defaults import get_cfg
    cfg = get_cfg()
    gen = WaymoScenarioGenerator(cfg)
    # for scenario in gen.scenarios:
    #     print(scenario)
    #     print(scenario.focused_tracks)
    #     break
    a, b = gen.get()
    for x in a.focused_tracks:
        b = x.partition_by("is_valid", as_dict=True)
        print(b.keys())
