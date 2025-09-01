# app/image_extractor/google_vision.py

from google.cloud import vision
import asyncio

def sync_text_detection(image_bytes: bytes) -> str:
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)

    response = client.annotate_image({
        'image': image,
        'features': [{'type': vision.Feature.Type.TEXT_DETECTION}]
    })

    if response.error.message:
        raise Exception(
            f'Google Vision API error: {response.error.message}\n'
            'For more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'
        )

    texts = response.text_annotations
    if texts:
        return texts[0].description.strip()
    return ""

async def extract_text_from_image(image_bytes: bytes) -> str:
    return await asyncio.to_thread(sync_text_detection, image_bytes)
