# app/logic/matcher.py
import re
from typing import List, Tuple
from bson import ObjectId  # type: ignore

from app.ai_ingredient_intelligence.db.mongodb import db


async def build_category_tree(collection, category_ids, name_field):
    """
    Given a collection and list of category ObjectIds, build a list of name paths.
    Example: [["Colorants", "Organic Colorants", "Natural Organic Colorants"]]
    """
    results = []
    for cid in category_ids:
        if not isinstance(cid, ObjectId):
            try:
                cid = ObjectId(cid)
            except:
                continue

        path = []
        current = await collection.find_one({"_id": cid})
        while current:
            path.insert(0, current.get(name_field))
            parent_id = current.get("parent_id")
            if parent_id:
                current = await collection.find_one({"_id": parent_id})
            else:
                current = None
        results.append(path)
    return results


async def match_inci_names(inci_names: List[str]) -> Tuple[List[dict], List[str]]:
    """
    Matches given INCI names against the branded_ingredients collection.
    Returns matches with description, functionality & chemical class trees.
    """

    branded_ingredients_col = db["ingre_branded_ingredients"]
    func_cat_col = db["ingre_functional_categories"]
    chem_class_col = db["ingre_chemical_classes"]

    # Normalize product INCI list
    product_inci_set = {name.strip().lower() for name in inci_names}

    matched_results = []

    # Fetch branded ingredients with their INCI and supplier name
    pipeline = [
        {
            "$lookup": {
                "from": "ingre_inci",
                "localField": "inci_ids",
                "foreignField": "_id",
                "as": "inci_docs"
            }
        },
        {
            "$lookup": {
                "from": "ingre_suppliers",
                "localField": "supplier_id",
                "foreignField": "_id",
                "as": "supplier_docs"
            }
        },
        {
            "$project": {
                "_id": 1,
                "ingredient_name": 1,
                "supplier_name": {"$arrayElemAt": ["$supplier_docs.supplierName", 0]},
                "description": 1,
                "functional_category_ids": 1,
                "chemical_class_ids": 1,
                "inci_list": "$inci_docs.inciName_normalized"
            }
        }
    ]

    async for doc in branded_ingredients_col.aggregate(pipeline):
        brand_inci_list = [i.strip().lower() for i in doc.get("inci_list", [])]
        brand_inci_set = set(brand_inci_list)
        total_brand_inci = len(brand_inci_set)

        if brand_inci_set.issubset(product_inci_set) and total_brand_inci > 0:
            func_tree = await build_category_tree(
                func_cat_col,
                doc.get("functional_category_ids", []),
                "functionalName"
            )
            chem_tree = await build_category_tree(
                chem_class_col,
                doc.get("chemical_class_ids", []),
                "chemicalClassName"
            )

            matched_results.append({
                "ingredient_name": doc["ingredient_name"],
                "supplier_name": doc.get("supplier_name"),  # FIXED: use the string from aggregation
                "description": doc.get("description"),
                "functionality_category_tree": func_tree,
                "chemical_class_category_tree": chem_tree,
                "match_score": 1.0,
                "matched_inci": list(brand_inci_set),
                "matched_count": total_brand_inci,
                "total_brand_inci": total_brand_inci
            })

    # Sort matches by number of INCI
    matched_results.sort(key=lambda x: x["total_brand_inci"], reverse=True)

    matched_inci_all = {inci for match in matched_results for inci in match["matched_inci"]}
    unmatched_terms = sorted(product_inci_set - matched_inci_all)

    return matched_results, unmatched_terms
