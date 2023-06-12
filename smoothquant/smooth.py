import torch
import torch.nn as nn

from transformers.models.opt.modeling_opt import OPTDecoderLayer
from transformers.models.bloom.modeling_bloom import BloomBlock

# from timm.models.vision_transformer import VisionTransformer
# from timm.models.vision_transformer import Attention


@torch.no_grad()
def smooth_ln_fcs(ln, fcs, act_scales, alpha=0.5):
    if not isinstance(fcs, list):
        fcs = [fcs]
    assert isinstance(ln, nn.LayerNorm)
    for fc in fcs:
        assert isinstance(fc, nn.Linear)
        assert ln.weight.numel() == fc.in_features == act_scales.numel()

    device, dtype = fcs[0].weight.device, fcs[0].weight.dtype
    act_scales = act_scales.to(device=device, dtype=dtype)
    weight_scales = torch.cat([fc.weight.abs().max(
        dim=0, keepdim=True)[0] for fc in fcs], dim=0)
    weight_scales = weight_scales.max(dim=0)[0].clamp(min=1e-5)

    scales = (act_scales.pow(alpha) / weight_scales.pow(1-alpha)
              ).clamp(min=1e-5).to(device).to(dtype)

    ln.weight.div_(scales)
    ln.bias.div_(scales)

    for fc in fcs:
        fc.weight.mul_(scales.view(1, -1))


@torch.no_grad()
def smooth_lm(model, scales, alpha=0.5):
    for name, module in model.named_modules():
        print('Name: ', name)
        print('Module: ', module)
        if isinstance(module, OPTDecoderLayer):
            attn_ln = module.self_attn_layer_norm
            qkv = [module.self_attn.q_proj,
                   module.self_attn.k_proj, module.self_attn.v_proj]
            qkv_input_scales = scales[name + '.self_attn.q_proj']
            smooth_ln_fcs(attn_ln, qkv, qkv_input_scales, alpha)

            ffn_ln = module.final_layer_norm
            fc1 = module.fc1
            fc1_input_scales = scales[name + '.fc1']
            smooth_ln_fcs(ffn_ln, fc1, fc1_input_scales, alpha)
        elif isinstance(module, BloomBlock):
            attn_ln = module.input_layernorm
            qkv = module.self_attention.query_key_value
            qkv_input_scales = scales[name + '.self_attention.query_key_value']
            smooth_ln_fcs(attn_ln, qkv, qkv_input_scales, alpha)

            ffn_ln = module.post_attention_layernorm
            fc1 = module.mlp.dense_h_to_4h
            fc1_input_scales = scales[name + '.mlp.dense_h_to_4h']
            smooth_ln_fcs(ffn_ln, fc1, fc1_input_scales, alpha)

@torch.no_grad()
def smooth_vit(model, scales, alpha=0.5, model_name='deit_'):
    if 'deit_' in model_name:
        print('DeiT_smooth')
        for i in range(len(model.blocks)):
            print(i)
            attn_ln = model.blocks[i].norm1
            qkv = model.blocks[i].attn.qkv
            qkv_input_scales = scales["model.blocks[%d].attn.qkv" %i]
            smooth_ln_fcs(attn_ln, qkv, qkv_input_scales, alpha)
            
            # proj = model.blocks[i].attn.proj
            # proj_input_scales = scales["model.blocks[%d].attn.proj" %i]
            # smooth_ln_fcs(attn_ln, proj, proj_input_scales, alpha)
            
            mlp_ln = model.blocks[i].norm2
            fc1 = model.blocks[i].mlp.fc1
            fc1_input_scales = scales["model.blocks[%d].mlp.fc1" %i]
            smooth_ln_fcs(mlp_ln, fc1, fc1_input_scales, alpha)           
            
            # fc2 = model.blocks[i].mlp.fc2
            # fc2_input_scales = scales["model.blocks[%d].mlp.fc2" %i]
            # smooth_ln_fcs(mlp_ln, fc2, fc2_input_scales, alpha)       
            
    elif 'mobilevit_' in model_name:
        print('MobileViT_smooth')
        for i in range(len(model.stages)):
            print('i: ', i)
            for j in range(len(model.stages[i])):
                print('j: ', j)
