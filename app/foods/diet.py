from foods.models import DietLabel


# Derive the user's diet
def derive_user_diet(food_diets):
    labels = { (d or "").lower() for d in food_diets if d }
    if DietLabel.OMNIVORE in labels:
        return DietLabel.OMNIVORE
    if DietLabel.VEGETARIAN in labels:
        return DietLabel.VEGETARIAN
    if DietLabel.VEGAN in labels:
        return DietLabel.VEGAN
    return DietLabel.UNKNOWN
