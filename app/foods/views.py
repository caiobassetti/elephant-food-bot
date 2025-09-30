from django.db.models import Prefetch
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import UserProfile, FavoriteFood, DietLabel
from .serializers import VegUserSerializer

class VegUsersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # One-to-one query with JOIN to pull 'catalog' relation (each food has it's catalog info)
        fav_qs = FavoriteFood.objects.select_related("catalog").order_by("pk")

        qs = (
            UserProfile.objects
            .filter(diet__in=[DietLabel.VEGAN, DietLabel.VEGETARIAN])
            # Many-to-many (customers have multiple food favorites)
            .prefetch_related(Prefetch("foods", queryset=fav_qs))
        )

        data = []
        for user in qs:
            favs = list(user.foods.all())
            top3 = [f.food_name for f in favs]
            data.append({
                "user_id": user.pk,
                "run_id": user.run_id,
                "diet": user.diet,
                "top3": top3,
            })

        ser = VegUserSerializer(data=data, many=True)
        ser.is_valid(raise_exception=True)
        return Response(ser.data)
