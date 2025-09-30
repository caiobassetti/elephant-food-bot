from rest_framework import serializers

class VegUserSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    run_id = serializers.UUIDField()
    diet = serializers.ChoiceField(choices=["vegan", "vegetarian"])
    top3 = serializers.ListField(
        child=serializers.CharField(max_length=120),
        min_length=1,
        max_length=3
    )
