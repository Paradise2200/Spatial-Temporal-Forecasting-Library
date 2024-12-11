
from layers.DGCN_related import *
from torch_utils.graph_process import *
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torch.nn import BatchNorm2d, Conv1d, Conv2d, ModuleList, Parameter,LayerNorm,InstanceNorm2d
"""
the parameters:
x-> [batch_num,in_channels,num_nodes,tem_size],
"""

'''模型总体根据GCN部分串联起来，LMLN部分作为辅助部分'''

class DGCN(nn.Module):
    def __init__(self, c_in, d_model,c_out, num_nodes,pred_len, week, day, recent, K, Kt):
        super(DGCN, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_2(c_in, d_model, num_nodes, tem_size, K, Kt)
        self.block2 = ST_BLOCK_2(d_model, d_model, num_nodes, tem_size, K, Kt)
        self.bn = BatchNorm2d(c_in, affine=False)

        self.conv1 = Conv2d(d_model, c_out, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv2 = Conv2d(d_model, c_out, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv3 = Conv2d(d_model, c_out, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv4 = Conv2d(d_model, c_out, kernel_size=(1, 2), padding=(0, 0),
                            stride=(1, 2), bias=True)

        self.h = Parameter(torch.zeros(num_nodes, num_nodes), requires_grad=True) # 可学习的邻接矩阵
        nn.init.uniform_(self.h, a=0, b=0.0001)
        self.pred_len=pred_len


    def forward(self, x_w, x_d, x_r,adj):
        '''输入特征维度(B,D,N,L)'''
        x_w = self.bn(x_w) # 对特征维度进行batch normalization 类似与ReVIN想法
        x_d = self.bn(x_d)
        x_r = self.bn(x_r)
        x = torch.cat((x_w, x_d, x_r), -1)

        adj =graph_laplace_trans(adj)
        A = self.h+torch.tensor(adj).to(self.h.device).float() # 固定的邻接矩阵+可学习的邻接矩阵。与ASTGCN不同的地方
        d = 1 / (torch.sum(A, -1) + 0.0001)
        D = torch.diag_embed(d) #对角化
        A = torch.matmul(D, A) # 矩阵乘上对角矩阵等价于元素相乘
        A1 = F.dropout(A, 0.5, self.training)
        # 输入和输出的时间长度是相同的
        x, _, _ = self.block1(x, A1) # 完成了整一个网络的流程
        x, d_adj, t_adj = self.block2(x, A1) # 堆叠
        # FIXME 这里需要根据不同的设置来调整
        assert x.shape[-1]//self.pred_len==5
        x1 = x[:, :, :, 0:self.pred_len]
        x2 = x[:, :, :, self.pred_len:2*self.pred_len]
        x3 = x[:, :, :, 2*self.pred_len:3*self.pred_len]
        x4 = x[:, :, :, 3*self.pred_len:]
        # FIXME 都已经经过了这么多的操作，还有周期之分吗？这里也感觉有点多余
        x1 = self.conv1(x1)
        x2 = self.conv2(x2)
        x3 = self.conv3(x3)
        x4 = self.conv4(x4)# 不同的周期使用的卷积不同
        x = x1 + x2 + x3 + x4 # b,c,n,l
        return x


###############################################################
# TODO 剩下的都是一些其他的模型
###############################################################

class DGCN_Res(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(DGCN_Res, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_1(c_in, d_model, num_nodes, tem_size, K, Kt)
        self.block2 = ST_BLOCK_1(d_model, d_model, num_nodes, tem_size, K, Kt)
        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv2 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv3 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv4 = Conv2d(d_model, 1, kernel_size=(1, 2), padding=(0, 0),
                            stride=(1, 2), bias=True)

        self.h = Parameter(torch.zeros(num_nodes, num_nodes), requires_grad=True)
        nn.init.uniform_(self.h, a=0, b=0.0001)

    def forward(self, x_w, x_d, x_r, supports):
        x_w = self.bn(x_w)
        x_d = self.bn(x_d)
        x_r = self.bn(x_r)
        x = torch.cat((x_w, x_d, x_r), -1)
        A = self.h + supports
        d = 1 / (torch.sum(A, -1) + 0.0001)
        D = torch.diag_embed(d)
        A = torch.matmul(D, A)
        A1 = F.dropout(A, 0.5, self.training)

        x, _, _ = self.block1(x, A1)
        x, d_adj, t_adj = self.block2(x, A1)

        x1 = x[:, :, :, 0:12]
        x2 = x[:, :, :, 12:24]
        x3 = x[:, :, :, 24:36]
        x4 = x[:, :, :, 36:60]

        x1 = self.conv1(x1).squeeze()
        x2 = self.conv2(x2).squeeze()
        x3 = self.conv3(x3).squeeze()
        x4 = self.conv4(x4).squeeze()  # b,n,l
        x = x1 + x2 + x3 + x4
        return x, d_adj, A


class DGCN_Mask(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(DGCN_Mask, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_1(c_in, d_model, num_nodes, tem_size, K, Kt)
        self.block2 = ST_BLOCK_1(d_model, d_model, num_nodes, tem_size, K, Kt)
        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv2 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv3 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv4 = Conv2d(d_model, 1, kernel_size=(1, 2), padding=(0, 0),
                            stride=(1, 2), bias=True)

        self.h = Parameter(torch.zeros(num_nodes, num_nodes), requires_grad=True)
        nn.init.uniform_(self.h, a=0, b=0.0001)

    def forward(self, x_w, x_d, x_r, supports):
        x_w = self.bn(x_w)
        x_d = self.bn(x_d)
        x_r = self.bn(x_r)
        x = torch.cat((x_w, x_d, x_r), -1)
        A = self.h * supports
        d = 1 / (torch.sum(A, -1) + 0.0001)
        D = torch.diag_embed(d)
        A1 = torch.matmul(D, A)
        # A1=F.dropout(A,0.5,self.training)

        x, _, _ = self.block1(x, A1)
        x, d_adj, t_adj = self.block2(x, A1)

        x1 = x[:, :, :, 0:12]
        x2 = x[:, :, :, 12:24]
        x3 = x[:, :, :, 24:36]
        x4 = x[:, :, :, 36:60]

        x1 = self.conv1(x1).squeeze()
        x2 = self.conv2(x2).squeeze()
        x3 = self.conv3(x3).squeeze()
        x4 = self.conv4(x4).squeeze()  # b,n,l
        x = x1 + x2 + x3 + x4
        return x, d_adj, A1


class DGCN_GAT(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(DGCN_GAT, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_3(c_in, d_model, num_nodes, tem_size, K, Kt)
        self.block2 = ST_BLOCK_3(d_model, d_model, num_nodes, tem_size, K, Kt)
        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv2 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv3 = Conv2d(d_model, 1, kernel_size=(1, 1), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.conv4 = Conv2d(d_model, 1, kernel_size=(1, 2), padding=(0, 0),
                            stride=(1, 2), bias=True)

        self.h = Parameter(torch.zeros(num_nodes, num_nodes), requires_grad=True)
        nn.init.uniform_(self.h, a=0, b=0.0001)

    def forward(self, x_w, x_d, x_r, supports):
        x_w = self.bn(x_w)
        x_d = self.bn(x_d)
        x_r = self.bn(x_r)
        x = torch.cat((x_w, x_d, x_r), -1)
        A = supports

        x, _, _ = self.block1(x, A)
        x, d_adj, t_adj = self.block2(x, A)

        x1 = x[:, :, :, 0:12]
        x2 = x[:, :, :, 12:24]
        x3 = x[:, :, :, 24:36]
        x4 = x[:, :, :, 36:60]

        x1 = self.conv1(x1).squeeze()
        x2 = self.conv2(x2).squeeze()
        x3 = self.conv3(x3).squeeze()
        x4 = self.conv4(x4).squeeze()  # b,n,l
        x = x1 + x2 + x3 + x4
        return x, d_adj, A




class DGCN_recent(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(DGCN_recent, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_2_r(c_in, d_model, num_nodes, recent, K, Kt)
        self.block2 = ST_BLOCK_2_r(d_model, d_model, num_nodes, recent, K, Kt)
        self.bn = BatchNorm2d(c_in, affine=False)
        # self.bn=LayerNorm([d_model,num_nodes,tem_size])
        self.conv1 = Conv2d(d_model, 1, kernel_size=(1, 2), padding=(0, 0),
                            stride=(1, 2), bias=True)

        self.h = Parameter(torch.zeros(num_nodes, num_nodes), requires_grad=True)
        nn.init.uniform_(self.h, a=0, b=0.0001)

    def forward(self, x_w, x_d, x_r, supports):
        x_r = self.bn(x_r)
        x = x_r

        A = self.h + supports
        d = 1 / (torch.sum(A, -1) + 0.0001)
        D = torch.diag_embed(d)
        A = torch.matmul(D, A)
        A1 = F.dropout(A, 0.5, self.training)

        x, _, _ = self.block1(x, A1)
        x, d_adj, t_adj = self.block2(x, A1)

        x = self.conv1(x).squeeze()  # b,n,l
        return x, d_adj, A


class LSTM(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(LSTM, self).__init__()
        self.lstm = nn.LSTM(c_in, d_model, batch_first=True)  # b*n,l,c
        self.d_model = d_model
        tem_size = week + day + recent
        self.tem_size = tem_size
        self.bn = BatchNorm2d(c_in, affine=False)

        self.conv1 = Conv2d(d_model, 12, kernel_size=(1, recent), padding=(0, 0),
                            stride=(1, 1), bias=True)

    def forward(self, x_w, x_d, x_r, supports):
        x_r = self.bn(x_r)
        x = x_r
        shape = x.shape
        h = Variable(torch.zeros((1, shape[0] * shape[2], self.d_model))).cuda()
        c = Variable(torch.zeros((1, shape[0] * shape[2], self.d_model))).cuda()
        hidden = (h, c)

        x = x.permute(0, 2, 3, 1).contiguous().view(shape[0] * shape[2], shape[3], shape[1])
        x, hidden = self.lstm(x, hidden)
        x = x.view(shape[0], shape[2], shape[3], self.d_model).permute(0, 3, 1, 2).contiguous()

        x = self.conv1(x).squeeze().permute(0, 2, 1).contiguous()  # b,n,l
        return x, supports, supports


class GRU(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(GRU, self).__init__()
        self.gru = nn.GRU(c_in, d_model, batch_first=True)  # b*n,l,c
        self.d_model = d_model
        tem_size = week + day + recent
        self.tem_size = tem_size
        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 12, kernel_size=(1, recent),
                            stride=(1, 1), bias=True)

    def forward(self, x_w, x_d, x_r, supports):
        x_r = self.bn(x_r)
        x = x_r
        shape = x.shape
        h = Variable(torch.zeros((1, shape[0] * shape[2], self.d_model))).cuda()
        hidden = h

        x = x.permute(0, 2, 3, 1).contiguous().view(shape[0] * shape[2], shape[3], shape[1])
        x, hidden = self.gru(x, hidden)
        x = x.view(shape[0], shape[2], shape[3], self.d_model).permute(0, 3, 1, 2).contiguous()
        x = self.conv1(x).squeeze().permute(0, 2, 1).contiguous()
        return x, supports, supports


class Gated_STGCN(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(Gated_STGCN, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_4(c_in, d_model, num_nodes, tem_size, K, Kt)
        self.block2 = ST_BLOCK_4(d_model, d_model, num_nodes, tem_size, K, Kt)
        self.block3 = ST_BLOCK_4(d_model, d_model, num_nodes, tem_size, K, Kt)

        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 12, kernel_size=(1, recent), padding=(0, 0),
                            stride=(1, 1), bias=True)
        self.d_model = d_model

    def forward(self, x_w, x_d, x_r, supports):
        x = self.bn(x_r)
        shape = x.shape

        x = self.block1(x, supports)
        x = self.block2(x, supports)
        x = self.block3(x, supports)
        x = self.conv1(x).squeeze().permute(0, 2, 1).contiguous()  # b,n,l
        return x, supports, supports


class GRCN(nn.Module):
    def __init__(self, c_in, d_model, num_nodes, week, day, recent, K, Kt):
        super(GRCN, self).__init__()
        tem_size = week + day + recent
        self.block1 = ST_BLOCK_5(c_in, d_model, num_nodes, recent, K, Kt)
        self.block2 = ST_BLOCK_5(d_model, d_model, num_nodes, recent, K, Kt)
        tem_size = week + day + recent
        self.tem_size = tem_size
        self.bn = BatchNorm2d(c_in, affine=False)
        self.conv1 = Conv2d(d_model, 12, kernel_size=(1, recent),
                            stride=(1, 1), bias=True)

    def forward(self, x_w, x_d, x_r, supports):
        x_r = self.bn(x_r)
        x = x_r
        shape = x.shape

        x = self.block1(x, supports)
        x = self.block2(x, supports)
        x = self.conv1(x).squeeze().permute(0, 2, 1).contiguous()
        return x, supports, supports