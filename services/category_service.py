import json
import os
from typing import Dict, List, Optional
import re


class CategoryService:
    def __init__(self, categories_file: str = "data/categories.json"):
        self.categories_file = categories_file
        self._ensure_categories_file()
        self.categories = self._load_categories()

    def _ensure_categories_file(self) -> None:
        """Ensure categories file exists."""
        os.makedirs(os.path.dirname(self.categories_file), exist_ok=True)
        if not os.path.exists(self.categories_file):
            self._save_categories(
                {
                    "keywords": {
                        "income": [
                            "получил",
                            "зачислили",
                            "перевели",
                            "пришло",
                            "нашёл",
                        ],
                        "expense": [
                            "потратил",
                            "заплатил",
                            "ушло",
                            "списали",
                            "купил",
                            "оплатил",
                        ],
                    },
                    "income": {
                        "Зарплата": ["зарплата", "зп", "оклад"],
                        "Подарок": ["подарок", "дар"],
                        "Перевод": ["перевод", "поступление"],
                    },
                    "expense": {
                        "Еда": ["продукты"],
                        "Транспорт": ["такси", "метро", "бензин", "проездной"],
                        "Здоровье": ["аптека", "врач"],
                        "Развлечения": ["кино", "театр", "ресторан", "кафе"],
                        "Перевод": ["перевод", "поступление"],
                    },
                }
            )

    @staticmethod
    def synonyms_to_category(
        category_to_synonyms: Dict[str, List[str]],
    ) -> Dict[str, str]:
        """Convert synonyms to keywords."""
        return {
            word: category
            for category, words in category_to_synonyms.items()
            for word in words
        }

    def _load_categories(self) -> Dict:
        """Load categories from file and transform for quick lookup."""
        try:
            with open(self.categories_file, "r", encoding="utf-8") as f:
                raw_categories = json.load(f)

            # Create a copy of the original structure
            categories = {
                "keywords": self.synonyms_to_category(raw_categories["keywords"]),
                "income": {
                    "categories": list(raw_categories["income"].keys()),
                    "keywords": {},
                },
                "expense": {
                    "categories": list(raw_categories["expense"].keys()),
                    "keywords": {},
                },
            }

            # Transform keywords for quick lookup
            for transaction_type in ["income", "expense"]:

                # Add the category itself as a keyword
                categories[transaction_type]["keywords"].update(
                    self.synonyms_to_category(raw_categories[transaction_type])
                )

            for transaction_type in ["income", "expense"]:
                for category in categories[transaction_type]["categories"]:
                    categories["keywords"][category.lower()] = transaction_type
            print(categories)
            return categories

        except Exception as e:
            print(f"Error loading categories: {e}")
            return {
                "keywords": {"income": {}, "expense": {}},
                "income": {"categories": [], "keywords": {}},
                "expense": {"categories": [], "keywords": {}},
            }

    def _save_categories(self, categories: Dict) -> None:
        """Save categories to file in the original format."""
        try:
            # Convert internal structure back to original format
            original_format = {
                "keywords": {
                    "income": list(categories["keywords"]["income"].keys()),
                    "expense": list(categories["keywords"]["expense"].keys()),
                },
                "income": {},
                "expense": {},
            }

            # Convert categories and keywords back to original format
            for transaction_type in ["income", "expense"]:
                for category in categories[transaction_type]["categories"]:
                    # Get all synonyms for this category
                    synonyms = []
                    for keyword, cat in categories[transaction_type][
                        "keywords"
                    ].items():
                        if cat == category and keyword != category.lower():
                            synonyms.append(keyword)
                    original_format[transaction_type][category] = synonyms

            with open(self.categories_file, "w", encoding="utf-8") as f:
                json.dump(original_format, f, ensure_ascii=False, indent=4)
            self.categories = categories
        except Exception as e:
            print(f"Error saving categories: {e}")

    def get_categories(self, transaction_type: str) -> List[str]:
        """Get list of categories for transaction type."""
        return self.categories.get(transaction_type, {}).get("categories", [])

    def get_keywords(self, transaction_type: str) -> Dict[str, str]:
        """Get keywords mapping for transaction type."""
        return self.categories.get(transaction_type, {}).get("keywords", {})

    def get_transaction_type_keywords(self, transaction_type: str) -> Dict[str, str]:
        """Get list of keywords for transaction type (income/expense)."""
        return self.categories.get("keywords", {}).get(transaction_type, {})

    def detect_transaction_type(self, text: str) -> Optional[str]:
        """Detect transaction type from text using keywords."""
        text = text.lower()
        words = text.split()

        # Check for transaction type keywords using dictionary lookup
        for word in words:
            clean_word = re.sub(r"[^\wа-яА-ЯёЁ]", "", word)
            if transaction_type := self.categories["keywords"].get(clean_word):
                return transaction_type
        print(words)
        return "expense"

    def add_category(self, transaction_type: str, category: str) -> bool:
        """Add new category."""
        if transaction_type not in ["income", "expense"]:
            return False

        if category not in self.categories[transaction_type]["categories"]:
            # Add to categories list
            self.categories[transaction_type]["categories"].append(category)
            # Add the category itself as a keyword
            self.categories[transaction_type]["keywords"][category.lower()] = category
            # Save in original format
            self._save_categories(self.categories)
            return True
        return False

    def add_keyword(self, transaction_type: str, keyword: str, category: str) -> bool:
        """Add new keyword for category."""
        if transaction_type not in ["income", "expense"]:
            return False

        if category not in self.categories[transaction_type]["categories"]:
            return False

        # Add keyword to internal structure
        self.categories[transaction_type]["keywords"][keyword.lower()] = category
        # Save in original format
        self._save_categories(self.categories)
        return True

    def detect_category(self, transaction_type: str, text: str) -> Optional[str]:
        """Detect category from text using keywords."""
        keywords = self.get_keywords(transaction_type)
        words = text.lower().split()

        for word in words:
            clean_word = re.sub(r"[^\wа-яА-ЯёЁ]", "", word)
            if category := keywords.get(clean_word):
                return category
        return None
