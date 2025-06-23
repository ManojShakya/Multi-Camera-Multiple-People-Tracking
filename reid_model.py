import torch
import torchvision.transforms as transforms
import numpy as np
import cv2
from PIL import Image
from fastreid.config import get_cfg
from fastreid.engine import default_setup
from fastreid.modeling import build_model
from fastreid.utils.checkpoint import Checkpointer

# ----------- Load FastReID Model --------------
def load_fastreid_model(config_file, weight_path):
    cfg = get_cfg()
    cfg.merge_from_file(config_file)
    cfg.MODEL.WEIGHTS = weight_path
    cfg.MODEL.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    cfg.freeze()
    
    model = build_model(cfg)
    Checkpointer(model).load(cfg.MODEL.WEIGHTS)
    model.eval()
    return model, cfg

config_file = "configs/Market1501/bagtricks_R50-ibn.yml"  # or another dataset config
#weights_path = "pretrained/bagtricks_R50-ibn.pth"         # download from FastReID Model Zoo

# config_file = 'bagtricks_R50-ibn.yml'
weights_path = 'market_bot_R50-ibn.pth'

reid_model, reid_cfg = load_fastreid_model(config_file, weights_path)

# ------------- Image Transforms ---------------
transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

# ------------- Feature Extractor ---------------
def extract_reid_feature(frame, box):
    x1, y1, x2, y2 = map(int, box)
    person_crop = frame[y1:y2, x1:x2]
    if person_crop.size == 0:
        return None

    try:
        img = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
        img_tensor = transform(img).unsqueeze(0).to(reid_cfg.MODEL.DEVICE)

        with torch.no_grad():
            features = reid_model(img_tensor)
        return features.squeeze().cpu().numpy()
    except Exception as e:
        print(f"[ERROR] Failed to extract ReID feature: {e}")
        return None


# def extract_reid_feature(frame, box):
#     x1, y1, x2, y2 = map(int, box)
#     person_crop = frame[y1:y2, x1:x2]

#     if person_crop.size == 0:
#         print("[WARNING] Empty crop encountered.")
#         return None

#     h, w = person_crop.shape[:2]
#     if h < 64 or w < 32:
#         print(f"[WARNING] Ignored too small crop: ({w}, {h})")
#         return None

#     try:
#         # Resize the crop to standard size (128x256)
#         crop_resized = cv2.resize(person_crop, (128, 256))
#         # Convert to PIL image for torchvision transform
#         img = Image.fromarray(cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB))
#         # Apply preprocessing: ToTensor + Normalize
#         img_tensor = transform(img).unsqueeze(0).to(reid_cfg.MODEL.DEVICE)

#         with torch.no_grad():
#             features = reid_model(img_tensor)
#         features = features.squeeze().cpu().numpy()
#         # L2-normalize the feature vector
#         norm = np.linalg.norm(features) + 1e-6
#         features /= norm
#         return features

#     except Exception as e:
#         print(f"[ERROR] Failed to extract ReID feature: {e}")
#         return None
