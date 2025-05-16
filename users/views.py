from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from focus.serializers import FocusDataSerializer
import json


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return Response({'error': '잘못된 JSON 형식입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        username = data.get('username')
        password = data.get('password')
        email = data.get('email')

        if not username or not password:
            return Response({'error': '아이디와 비밀번호는 필수입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({'error': '이미 존재하는 사용자입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        User.objects.create_user(username=username, password=password, email=email)
        return Response({'message': '회원가입 성공!'}, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(request, username=username, password=password)

    if user is not None:
        return Response({'message': '로그인 성공!'})
    else:
        return Response({'error': '아이디 또는 비밀번호가 올바르지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request):
    user = request.user
    focus_qs = user.focus_data.order_by('-timestamp')
    focus_serializer = FocusDataSerializer(focus_qs, many=True)

    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'focus_data': focus_serializer.data
    }
    return Response(data, status=status.HTTP_200_OK)
