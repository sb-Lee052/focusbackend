# focus/rl_model.py
import torch
import torch.nn as nn
import torch.nn.functional as F

class PolicyNet(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, output_dim=2):
        super().__init__()
        # 예시: 두 개의 완전연결 레이어
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        # 출력: [prob_continue, prob_break] 같은 2-차원 액션 확률
        return F.softmax(self.fc2(x), dim=-1)