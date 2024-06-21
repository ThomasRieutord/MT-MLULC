from torch import nn
import torch
import torch.utils.checkpoint as checkpoint

from mmt.graphs.models.custom_layers import down_block
from mmt.graphs.models.custom_layers import up_block
from mmt.graphs.models.custom_layers import double_conv

Down = down_block.Down
Up = up_block.Up
DoubleConv = double_conv.DoubleConv

class CrossChannelAttention(nn.Module):
    """Module computing attention across channels"""
    def __init__(self, in_channels, qk_channels=10):
        super(CrossChannelAttention, self).__init__()
        self.query_conv = nn.Conv2d(in_channels, qk_channels, kernel_size=1)
        self.key_conv = nn.Conv2d(in_channels, qk_channels, kernel_size=1)
        self.value_conv = nn.Conv2d(in_channels, in_channels, kernel_size=1)
        self.gamma = nn.Parameter(torch.zeros(1))
    
    def forward(self, x):
        q = self.query_conv(x).permute(0,3,2,1)
        k = self.key_conv(x).permute(0,3,2,1)
        v = self.value_conv(x).permute(0,3,2,1)
        attention = nn.functional.scaled_dot_product_attention(q, k, v).permute(0,3,2,1)
        out = self.gamma * attention + x
        return out
    
    def check_shapes(self, x = None):
        """Display shapes of some tensors"""
        if x is None:
            x = torch.rand(10, 3, 600, 300)
            print(f"Random input: x = {x.shape}")
        else:
            print(f"Given input: x = {x.shape}")
        
        q = self.query_conv(x).permute(0,3,2,1).contiguous()
        print(f"q = {q.shape}")
        k = self.key_conv(x).permute(0,3,2,1).contiguous()
        print(f"k = {k.shape}")
        v = self.value_conv(x).permute(0,3,2,1).contiguous()
        print(f"v = {v.shape}")
        attention = nn.functional.scaled_dot_product_attention(q, k, v).permute(0,3,2,1)
        print(f"attention = {attention.shape}")
        out = self.gamma * attention + x
        print(f"out = {out.shape}")
        

class AtrouMMU(nn.Module):
    def __init__(self, inf, scale_factor=10, bias=False):
        super(AtrouMMU, self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(
                inf, inf, kernel_size=3, padding=1, stride=scale_factor, bias=bias
            ),
            nn.GroupNorm(1, inf),
            nn.ReLU(),
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(
                inf,
                inf,
                kernel_size=3,
                padding=6,
                dilation=6,
                stride=scale_factor,
                bias=bias,
            ),
            nn.GroupNorm(1, inf),
            nn.ReLU(),
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(
                inf,
                inf,
                kernel_size=3,
                padding=12,
                dilation=12,
                stride=scale_factor,
                bias=bias,
            ),
            nn.GroupNorm(1, inf),
            nn.ReLU(),
        )
        self.conv4 = nn.Sequential(
            nn.Conv2d(
                inf,
                inf,
                kernel_size=3,
                padding=18,
                dilation=18,
                stride=scale_factor,
                bias=bias,
            ),
            nn.GroupNorm(1, inf),
            nn.ReLU(),
        )
        self.avg = nn.AvgPool2d(scale_factor)
        self.fin = nn.Conv2d(inf * 5, inf, kernel_size=1)

    def forward(self, x):
        x1 = self.conv1(x)
        x2 = self.conv2(x)
        x3 = self.conv3(x)
        x4 = self.conv4(x)
        x5 = self.avg(x)
        x = torch.cat((x1, x2, x3, x4, x5), 1)
        return self.fin(x)


class Upsample(nn.Module):
    def __init__(self, scale_factor=2, mode="nearest"):
        super(Upsample, self).__init__()
        self.scale_factor = scale_factor
        self.mode = mode

    def forward(self, x):
        return torch.nn.functional.interpolate(
            x, scale_factor=self.scale_factor, mode=self.mode
        )

class CrossResolutionAttention(nn.Module):
    def __init__(self, in_channels, out_channels, resize = 1):
        super().__init__()
        print(f"Init {self.__class__.__name__} with in_channels={in_channels}, out_channels={out_channels}, resize = {resize}")
        if resize is None:
            resize = 1
        
        self.query_conv = nn.Conv2d(in_channels, out_channels, kernel_size=resize, stride = resize)
        self.key_conv = nn.Conv2d(in_channels, out_channels, kernel_size=resize, stride = resize)
        self.value_conv = nn.Conv2d(in_channels, out_channels, kernel_size=resize, stride = resize)
    
    def forward(self, x):
        q = self.query_conv(x).permute(0,3,2,1).contiguous()
        k = self.key_conv(x).permute(0,3,2,1).contiguous()
        v = self.value_conv(x).permute(0,3,2,1).contiguous()
        attention = nn.functional.scaled_dot_product_attention(q, k, v).permute(0,3,2,1)
        return attention
    
    def check_shapes(self, x = None):
        """Display shapes of some tensors"""
        if x is None:
            x = torch.rand(10, 3, 600, 300)
            print(f"Random input: x = {x.shape}")
        else:
            print(f"Given input: x = {x.shape}")
        
        q = self.query_conv(x).permute(0,3,2,1)
        print(f"q = {q.shape}")
        k = self.key_conv(x).permute(0,3,2,1)
        print(f"k = {k.shape}")
        v = self.value_conv(x).permute(0,3,2,1)
        print(f"v = {v.shape}")
        attention = nn.functional.scaled_dot_product_attention(q, k, v).permute(0,3,2,1)
        print(f"attention = {attention.shape}")


class InterpConv(nn.Module):
    def __init__(self, in_channels, out_channels, resize, kernel_size = 1, mode="bilinear"):
        super().__init__()
        if resize is None:
            resize = 1
        
        self.scale_factor = kernel_size * resize
        self.mode = mode
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size = kernel_size, stride = kernel_size)

    def forward(self, x):
        x = torch.nn.functional.interpolate(
            x, scale_factor=self.scale_factor, mode=self.mode
        )
        x = self.conv(x)
        return x


class AttnInterpAttn(nn.Module):
    def __init__(self, in_channels, out_channels, resize = 1):
        super().__init__()
        print(f"Init {self.__class__.__name__} with in_channels={in_channels}, out_channels={out_channels}, resize = {resize}")
        
        self.attn1 = CrossChannelAttention(in_channels)
        self.interp = InterpConv(in_channels, out_channels, resize = resize)
        self.attn2 = CrossChannelAttention(out_channels)
        
    def forward(self, x):
        x = self.attn1(x)
        x = self.interp(x)
        x = self.attn2(x)
        return x

class AutoEncoder2(nn.Module):
    def __init__(self, in_channels, out_channels, emb_channels = 50, resize = 1):
        super().__init__()
        if resize is None:
            resize = 1
        
        self.encoder = AttnInterpAttn(in_channels, emb_channels, resize = 1/resize)
        self.decoder = AttnInterpAttn(emb_channels, out_channels, resize = resize)
        
    def forward(self, x):
        emb = self.encoder(x)
        return emb, self.decoder(emb)

class AttentionEncoder(nn.Module):
    def __init__(self, in_channels, out_channels, resize = 1):
        super().__init__()
        print(f"Init {self.__class__.__name__} with in_channels={in_channels}, out_channels={out_channels}, resize = {resize}")
        if resize is None:
            resize = 1
        
        self.attn1 = CrossChannelAttention(in_channels, in_channels)
        self.attn2 = CrossResolutionAttention(in_channels=in_channels, out_channels=out_channels, resize=resize)
        self.attn3 = CrossChannelAttention(out_channels, out_channels)
        
    def forward(self, x):
        x = self.attn1(x)
        x = self.attn2(x)
        x = self.attn3(x)
        return x

class AttentionDecoder(nn.Module):
    def __init__(self, in_channels, out_channels, resize = 1):
        super().__init__()
        print(f"Init {self.__class__.__name__} with in_channels={in_channels}, out_channels={out_channels}, resize = {resize}")
        if resize is None:
            resize = 1
        
        self.attn1 = CrossChannelAttention(in_channels, in_channels)
        self.attn2 = CrossResolutionAttention(in_channels=in_channels, out_channels=out_channels, resize=resize)
        self.attn3 = CrossChannelAttention(out_channels, out_channels)
        
    def forward(self, x):
        x = self.attn1(x)
        x = self.attn2(x)
        x = self.attn3(x)
        return x
    
class SimpleDecoder(nn.Module):
    """
    This class represents the tail of ResNet. It performs a global pooling and maps the output to the
    correct class by using a fully connected layer.
    """

    def __init__(
        self,
        in_features,
        n_classes,
        depth=1,
        num_groups=4,
        nf=52,
        resize=None,
        atrou=True,
        bias=False,
    ):
        super().__init__()
        # self.pre=torch.nn.PixelShuffle(6)
        if num_groups is None:
            num_groups = nf

        self.decoder = torch.nn.Sequential()
        inc = in_features
        if resize is not None:
            if atrou:
                self.decoder.add_module(
                    "pool", AtrouMMU(inc, scale_factor=resize, bias=bias)
                )
            else:
                self.decoder.add_module("pool", nn.MaxPool2d(resize))
        for i in range(1, depth):
            self.decoder.add_module(
                f"conv_{i}",
                nn.Conv2d(inc, nf, kernel_size=3, padding=1, bias=bias),
            )
            self.decoder.add_module(
                f"groupnorm_{i}", nn.GroupNorm(num_groups, nf)
            )
            self.decoder.add_module(f"relu_{i}", nn.ReLU(inplace=True))
            inc = nf
        self.decoder.add_module(f"attn_{depth}f", CrossChannelAttention(inc, 10))
        self.decoder.add_module(f"conv_{depth}", nn.Conv2d(inc, n_classes, 1))

    def forward(self, x):
        x = self.decoder(x)
        return x

class SimpleAttentionDecoder(nn.Module):
    """
    This class represents the tail of ResNet. It performs a global pooling and maps the output to the
    correct class by using a fully connected layer.
    """

    def __init__(
        self,
        in_features,
        n_classes,
        depth=1,
        num_groups=4,
        nf=52,
        resize=None,
        atrou=True,
        bias=False,
    ):
        super().__init__()
        self.resize = resize
        
        if num_groups is None:
            num_groups = nf
            
        if resize is not None:
            if atrou:
                self.pool = AtrouMMU(in_features, scale_factor=resize, bias=bias)
            else:
                self.pool = nn.MaxPool2d(resize)
        
        self.attn1 = CrossChannelAttention(in_features, 10)
        self.conv1 = nn.Conv2d(in_features, n_classes, 1)
        
    def forward(self, x):
        if self.resize is not None:
            x = self.pool(x)
            
        # x = self.attn1(x)
        x = self.conv1(x)
        return x


class AttentionUNet(nn.Module):
    def __init__(
        self,
        input_channels,
        number_feature_map=32,
        embedding_dim=32,
        mode="light",
        num_groups=None,
        up_mode="bilinear",
        memory_monger=False,
        resize=None,
        pooling_factors=[2, 2, 2, 2, 3],
        tlm_p=0,
        bias=False,
    ):
        down_mode = "maxpool"
        super().__init__()
        self.embedding_dim = embedding_dim
        self.cross_channel_attention = CrossChannelAttention(number_feature_map, 10)
        cca = self.cross_channel_attention
        
        if resize is not None:
            self.inc = nn.Sequential(
                Upsample(scale_factor=resize, mode="nearest"),
                DoubleConv(
                    input_channels, number_feature_map, num_groups=num_groups, bias=bias
                ),
            )
        else:
            self.inc = DoubleConv(
                input_channels, number_feature_map, num_groups=num_groups, bias=bias
            )
        if mode == "light":
            self.down1 = Down(
                number_feature_map,
                number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[0],
                bias=bias,
            )
            self.down2 = Down(
                number_feature_map,
                number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[1],
                bias=bias,
            )
            self.down3 = nn.Sequential(
                Down(
                    number_feature_map,
                    number_feature_map,
                    mode=down_mode,
                    num_groups=num_groups,
                    factor=pooling_factors[2],
                    bias=bias,
                ),
                CrossChannelAttention(number_feature_map, 10)
            )
            self.down4 = nn.Sequential(
                Down(
                    number_feature_map,
                    number_feature_map,
                    mode=down_mode,
                    num_groups=num_groups,
                    factor=pooling_factors[3],
                    bias=bias,
                ),
                CrossChannelAttention(number_feature_map, 10)
            )
            # self.down3 = Down(
                # number_feature_map,
                # number_feature_map,
                # mode=down_mode,
                # num_groups=num_groups,
                # factor=pooling_factors[2],
                # bias=bias,
            # )
            # self.down4 = Down(
                # number_feature_map,
                # number_feature_map,
                # mode=down_mode,
                # num_groups=num_groups,
                # factor=pooling_factors[3],
                # bias=bias,
            # )
            self.down5 = Down(
                number_feature_map,
                number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[4],
                bias=bias,
            )
            self.up1 = Up(
                number_feature_map * 2,
                number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-1],
                bias=bias,
            )
            self.up2 = Up(
                number_feature_map * 2,
                number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-2],
                bias=bias,
            )
            self.up3 = Up(
                number_feature_map * 2,
                number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-3],
                bias=bias,
            )
            self.up4 = Up(
                number_feature_map * 2,
                number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-4],
                bias=bias,
            )
            self.up5 = Up(
                number_feature_map * 2,
                number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-5],
                bias=bias,
            )
            self.outc = nn.Conv2d(number_feature_map, embedding_dim, kernel_size=1)

        elif mode == "heavy":
            self.down1 = Down(
                number_feature_map,
                2 * number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[0],
                bias=bias,
            )
            self.down2 = Down(
                2 * number_feature_map,
                2 * number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[1],
                bias=bias,
            )
            self.down3 = Down(
                2 * number_feature_map,
                4 * number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[2],
                bias=bias,
            )
            self.down4 = Down(
                4 * number_feature_map,
                8 * number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[3],
                bias=bias,
            )
            self.down5 = Down(
                8 * number_feature_map,
                8 * number_feature_map,
                mode=down_mode,
                num_groups=num_groups,
                factor=pooling_factors[4],
                bias=bias,
            )
            self.up1 = Up(
                16 * number_feature_map,
                8 * number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-1],
                bias=bias,
            )
            self.up2 = nn.Sequential(
                Up(
                    12 * number_feature_map,
                    4 * number_feature_map,
                    up_mode,
                    num_groups=num_groups,
                    factor=pooling_factors[-2],
                    bias=bias,
                ),
                CrossChannelAttention(number_feature_map, 10)
            )
            self.up3 = nn.Sequential(
                Up(
                    6 * number_feature_map,
                    2 * number_feature_map,
                    up_mode,
                    num_groups=num_groups,
                    factor=pooling_factors[-3],
                    bias=bias,
                ),
                CrossChannelAttention(number_feature_map, 10)
            )
            self.up4 = Up(
                4 * number_feature_map,
                2 * number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-4],
                bias=bias,
            )
            self.up5 = Up(
                3 * number_feature_map,
                2 * number_feature_map,
                up_mode,
                num_groups=num_groups,
                factor=pooling_factors[-5],
                bias=bias,
            )
            self.outc = nn.Conv2d(2 * number_feature_map, embedding_dim, kernel_size=1)

        self.forward_method = self.classical_forward
        if memory_monger:
            self.dummy_tensor = torch.ones(1, dtype=torch.float32, requires_grad=True)
            self.encoder_wrapper = ModuleWrapperIgnores2ndArg(self.encoder_part)
            self.forward_method = self.MemoryMonged_forward

    def encoder_part(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x6 = self.down5(x5)
        return x1, x2, x3, x4, x5, x6

    def decoder_part(self, x1, x2, x3, x4, x5, x6):
        x = self.up1(x6, x5)
        x = self.up2(x, x4)
        x = self.up3(x, x3)
        x = self.up4(x, x2)
        x = self.up5(x, x1)
        return self.outc(x)
    
    def classical_forward(self, x):
        x1, x2, x3, x4, x5, x6 = self.encoder_part(x)
        return self.decoder_part(x1, x2, x3, x4, x5, x6)

    def MemoryMonged_forward(self, x):
        x1, x2, x3, x4, x5, x6 = checkpoint.checkpoint(
            self.encoder_wrapper, x, self.dummy_tensor
        )
        return self.decoder_part(x1, x2, x3, x4, x5, x6)

    def forward(self, x):
        return self.forward_method(x)


class TransformerEmbedding(nn.Module):
    def __init__(
        self,
        in_channels,
        n_classes,
        cat=False,
        mul=False,
        softpos=False,
        mode="light",
        number_feature_map=None,
        n_channels_hiddenlay=30,
        embedding_dim=None,
        n_channels_embedding=32,
        memory_monger=False,
        num_groups=None,
        up_mode="bilinear",
        decoder_depth=1,
        resize=None,
        pooling_factors=[3, 3, 3, 3, 3],
        encoder=AttentionUNet,
        decoder=SimpleAttentionDecoder,
        decoder_atrou=True,
        tlm_p=0,
        bias=False,
        image_operator="mul",
    ):
        super().__init__()
        if number_feature_map is not None:
            n_channels_hiddenlay = number_feature_map
            print(f"<{self.__class__.__name__}>mmt-0.2 API changes: 'number_feature_map' is now renamed 'n_channels_hiddenlay'. Please use it for now on. Current value: n_channels_hiddenlay={n_channels_hiddenlay}")
        
        if embedding_dim is not None:
            n_channels_embedding = embedding_dim
            print(f"<{self.__class__.__name__}>mmt-0.2 API changes: 'embedding_dim' is now renamed 'n_channels_hiddenlay'. Please use it for now on. Current value: n_channels_embedding={n_channels_embedding}")
        
        if not isinstance(resize, list):
            enc_resize = resize
            dec_resize = resize
        else:
            enc_resize = resize[0]
            dec_resize = resize[1]
        self.encoder = encoder(
            in_channels,
            number_feature_map=number_feature_map,
            embedding_dim=embedding_dim,
            mode=mode,
            num_groups=num_groups,
            up_mode=up_mode,
            memory_monger=True,
            resize=enc_resize,
            pooling_factors=pooling_factors,
            tlm_p=tlm_p,
            bias=bias,
        )
        in_dec = self.encoder.embedding_dim
        self.cat = cat
        self.mul = mul
        self.softpos = softpos
        if cat:
            in_dec = in_dec * 2
        self.decoder = decoder(
            in_dec,
            n_classes,
            resize=dec_resize,
        )
        # self.decoder = decoder(
            # in_dec,
            # n_classes,
            # depth=decoder_depth,
            # num_groups=num_groups,
            # nf=number_feature_map,
            # resize=dec_resize,
            # atrou=decoder_atrou,
            # bias=bias,
        # )
        
        if resize is None:
            resize = 1
        self.encoder = AttnInterpAttn(in_channels, embedding_dim, resize = 1/resize)
        self.decoder = AttnInterpAttn(embedding_dim, n_classes, resize = resize)
        
        self.forward_method = self.classical_forward
        if memory_monger:
            self.dummy_tensor = torch.ones(1, dtype=torch.float32, requires_grad=True)
            self.encoder_wrapper = ModuleWrapperIgnores2ndArg(self.encoder)
            self.forward_method = self.MemoryMonged_forward
        self.n_classes = n_classes
        self.image_mul = False
        if image_operator == "mul":
            self.image_mul = True

    def classical_forward(self, x, full=False, res=None, image=None):
        if full:
            x = self.encoder(x)
        if res is not None:
            if self.softpos:
                res = torch.softmax(res, 1)
            if self.cat:
                x = torch.cat((x, res), 1)
            elif self.mul:
                x *= res
            else:
                x += res
        if image is not None:
            if self.image_mul:
                x *= image
            else:
                x += image
        return x, self.decoder(x)

    def MemoryMonged_forward(self, x, full=False, res=None, image=None):
        if full:
            x = checkpoint.checkpoint(self.encoder_wrapper, x, self.dummy_tensor)
        if res is not None:
            if self.softpos:
                res = torch.softmax(res, 1)
            if self.cat:
                x = torch.cat((x, res), 1)
            elif self.mul:
                x *= res
            else:
                x += res
        if image is not None:
            if self.image_mul:
                x *= image
            else:
                x += image
        return x, self.decoder(x)

    def forward(self, x, full=False, res=None, image=None):
        return self.forward_method(x, full, res, image)


class ModuleWrapperIgnores2ndArg(nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, x, dummy_arg=None):
        assert dummy_arg is not None
        x = self.module(x)
        return x


class ModuleWrapperIgnores6rdArg(nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, x, im0, im1, im2, im3, im4, im5, dummy_arg=None):
        assert dummy_arg is not None
        x = self.module(x, im0, im1, im2, im3, im4, im5)
        return x


class ModuleWrapperIgnores2ndArg(nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, x, dummy_arg=None):
        assert dummy_arg is not None
        x = self.module(x)
        return x


class ModuleWrapperIgnores6rdArg(nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, x, im0, im1, im2, im3, im4, im5, dummy_arg=None):
        assert dummy_arg is not None
        x = self.module(x, im0, im1, im2, im3, im4, im5)
        return x