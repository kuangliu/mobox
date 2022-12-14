import torch
import torch.nn as nn
import torch.nn.functional as F

from einops import repeat, rearrange

from mobox.layers.mlp import MLP
from mobox.layers.vectornet import VectorNetEncoder
from mobox.layers.temporal_encoder import TemporalEncoder
from mobox.layers.position_encoding import positional_encoding

from mobox.models import MODEL_REGISTRY

from projects.wayformer.loss import MyLoss
from projects.wayformer.transformer import Transformer


@MODEL_REGISTRY.register()
class Wayformer(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        T = cfg.TRACK.FUTURE_SIZE
        M = cfg.MODEL.OUTPUT_MODES

        d_model = 256
        # self.encoder_agent = MLP(7, d_model)
        # self.encoder_nearby = MLP(7, d_model)
        # self.encoder_map = MLP(236, d_model)
        # self.encoder_agent = VectorNetEncoder(7, d_model)
        # self.encoder_nearby = VectorNetEncoder(7, d_model)
        # self.encoder_map = VectorNetEncoder(4, d_model)
        self.encoder_agent = TemporalEncoder(7, d_model, 10)
        self.encoder_nearby = TemporalEncoder(7, d_model, 10)
        self.encoder_map = TemporalEncoder(4, d_model, 59)

        self.transformer = Transformer(d_model)
        self.query_embed = nn.Embedding(M, d_model)

        self.cls_head = MLP(d_model, 1)
        self.reg_head = MLP(d_model, T*2)

        self.loss = MyLoss()

        d = torch.load("./cache/anchors.pth")
        # self.ref = nn.Parameter(d)
        self.register_buffer("ref", d)

        self.apply(self.init_weights)
        self.reset_parameters()

    def reset_parameters(self):
        # Reference: https://github.com/IDEA-Research/detrex/blob/main/projects/dab_detr/modeling/dab_detr.py#L129
        nn.init.constant_(self.reg_head.layers[-1].weight, 0)
        nn.init.constant_(self.reg_head.layers[-1].bias, 0)

    def init_weights(self, m):
        # Reference: https://github.com/facebookresearch/mae/blob/main/models_mae.py#L85
        if isinstance(m, nn.Linear):
            # we use xavier_uniform following official JAX ViT:
            torch.nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)

    def get_pos_encoding(self, x):
        N, L, D = x.shape
        pos_embed = positional_encoding(L, D)
        return pos_embed

    def forward(self, xs):
        # Encoder.
        x_agent = self.encoder_agent(xs["agent"])     # [N,1,D]
        x_nearby = self.encoder_nearby(xs["nearby"])  # [N,S_a,D]
        x_map = self.encoder_map(xs["map"])           # [N,S_r,D]

        # Early fusion.
        # x_agent = x_agent.flatten(1, 2)
        # x_nearby = x_nearby.flatten(1, 2)
        # x_map = x_map.flatten(1, 2)
        x = torch.cat([x_agent, x_nearby, x_map], dim=1)

        # Transformer.
        attn_mask = None
        pos_embed = self.get_pos_encoding(x)
        out = self.transformer(x, attn_mask=attn_mask,
                               query_embed=self.query_embed.weight, pos_embed=pos_embed)

        # Predict.
        cls_out = self.cls_head(out)
        reg_out = self.reg_head(out)
        N, M = reg_out.shape[:2]
        cls_out = cls_out.squeeze(-1)
        reg_out = reg_out.view(N, M, -1, 2) + self.ref

        if self.training:
            targets = xs["target"]
            loss = self.loss(cls_out, reg_out, targets)
            return loss
        return cls_out, reg_out


def test_model():
    from config.defaults import get_cfg
    from mobox.models import build_model
    from mobox.datasets import construct_loader
    from projects.wayformer.dataset import WaymoDataset
    cfg = get_cfg()
    model = build_model(cfg)
    dataloader = construct_loader(cfg, mode="train")
    for i, inputs in enumerate(dataloader):
        model(inputs)
        break


if __name__ == "__main__":
    test_model()
