"""
Hybrid Face Filter Module
Uses MediaPipe when available, falls back to OpenCV for better compatibility
"""

import cv2
import numpy as np
from PIL import Image
import os
import warnings
import logging
from typing import List, Tuple, Optional, Dict
from ..core.config import settings

# Suppress MediaPipe/TensorFlow Lite warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TensorFlow warnings
os.environ['ABSL_MIN_LOG_LEVEL'] = '2'  # Suppress absl logging warnings
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', category=UserWarning, module='mediapipe')
warnings.filterwarnings('ignore', message='.*Feedback manager.*')

# Try to import MediaPipe, fall back to OpenCV if not available
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    print("MediaPipe loaded successfully - using advanced face detection")
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("MediaPipe not available - using OpenCV fallback")

class HybridFaceFilter:
    def __init__(self):
        """Initialize the Hybrid Face Filter with best available detection method."""
        self.use_mediapipe = MEDIAPIPE_AVAILABLE
        
        if self.use_mediapipe:
            # Initialize MediaPipe components
            self.mp_face_detection = mp.solutions.face_detection
            self.mp_face_mesh = mp.solutions.face_mesh
            self.mp_drawing = mp.solutions.drawing_utils
            
            self.face_detection = self.mp_face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5
            )
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        else:
            # Initialize OpenCV components
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
    
    def detect_face_mediapipe(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Detect face using MediaPipe (more accurate)"""
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_detection.process(rgb_image)
        
        if results.detections:
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            h, w, _ = image.shape
            
            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)
            
            return (x, y, width, height)
        
        return None
    
    def detect_face_opencv(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Detect face using OpenCV (fallback)"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        
        if len(faces) > 0:
            largest_face = max(faces, key=lambda x: x[2] * x[3])
            return tuple(largest_face)
        
        return None
    
    def detect_face(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Detect face using the best available method"""
        if self.use_mediapipe:
            return self.detect_face_mediapipe(image)
        else:
            return self.detect_face_opencv(image)
    
    def get_face_landmarks_mediapipe(self, image: np.ndarray) -> Optional[object]:
        """Get facial landmarks using MediaPipe"""
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_image)
        
        if results.multi_face_landmarks:
            return results.multi_face_landmarks[0]
        
        return None
    
    def get_face_landmarks_opencv(self, image: np.ndarray, face_bbox: Tuple[int, int, int, int]) -> List[Tuple[int, int]]:
        """Get approximate facial landmarks using OpenCV"""
        x, y, w, h = face_bbox
        face_roi = image[y:y+h, x:x+w]
        gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        
        eyes = self.eye_cascade.detectMultiScale(gray_face, 1.1, 3)
        
        landmarks = []
        for (ex, ey, ew, eh) in eyes:
            # Convert to absolute coordinates
            landmarks.append((x + ex + ew//2, y + ey + eh//2))
        
        return landmarks
    
    def create_face_mask_mediapipe(self, image: np.ndarray, landmarks: object) -> np.ndarray:
        """Create face mask using MediaPipe landmarks"""
        h, w, _ = image.shape
        mask = np.zeros((h, w), dtype=np.uint8)
        
        # Get face contour points
        face_oval = mp.solutions.face_mesh.FACEMESH_FACE_OVAL
        face_points = []
        
        for connection in face_oval:
            start_idx = connection[0]
            end_idx = connection[1]
            
            start_point = landmarks.landmark[start_idx]
            end_point = landmarks.landmark[end_idx]
            
            start_x = int(start_point.x * w)
            start_y = int(start_point.y * h)
            end_x = int(end_point.x * w)
            end_y = int(end_point.y * h)
            
            face_points.extend([(start_x, start_y), (end_x, end_y)])
        
        # Create convex hull for face contour
        if face_points:
            face_points = np.array(face_points)
            hull = cv2.convexHull(face_points.astype(np.int32))
            cv2.fillPoly(mask, [hull], 255)
        
        # Apply mask to image
        masked_image = image.copy()
        masked_image[mask == 0] = [0, 0, 0]
        
        return masked_image
    
    def create_face_mask_opencv(self, image: np.ndarray, face_bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Create face mask using OpenCV"""
        h, w, _ = image.shape
        mask = np.zeros((h, w), dtype=np.uint8)
        
        x, y, w_face, h_face = face_bbox
        
        # Create elliptical mask for more natural face shape
        center = (x + w_face // 2, y + h_face // 2)
        axes = (w_face // 2, h_face // 2)
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
        
        # Apply mask to image
        masked_image = image.copy()
        masked_image[mask == 0] = [0, 0, 0]
        
        return masked_image
    
    def blacken_eyes_and_lips_mediapipe(self, image: np.ndarray, landmarks: object) -> np.ndarray:
        """Blacken eyes and lips using MediaPipe landmarks"""
        result_image = image.copy()
        h, w, _ = image.shape
        
        # Eye landmarks (left and right eye)
        left_eye_indices = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        right_eye_indices = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
        
        # Lip landmarks
        lip_indices = [61, 84, 17, 314, 405, 320, 307, 375, 321, 308, 324, 318, 13, 82, 81, 80, 78, 95, 88, 178, 87, 14, 317, 402, 318, 324]
        
        # Blacken left eye
        left_eye_points = []
        for idx in left_eye_indices:
            point = landmarks.landmark[idx]
            x = int(point.x * w)
            y = int(point.y * h)
            left_eye_points.append((x, y))
        
        if left_eye_points:
            left_eye_points = np.array(left_eye_points)
            hull = cv2.convexHull(left_eye_points.astype(np.int32))
            cv2.fillPoly(result_image, [hull], (0, 0, 0))
        
        # Blacken right eye
        right_eye_points = []
        for idx in right_eye_indices:
            point = landmarks.landmark[idx]
            x = int(point.x * w)
            y = int(point.y * h)
            right_eye_points.append((x, y))
        
        if right_eye_points:
            right_eye_points = np.array(right_eye_points)
            hull = cv2.convexHull(right_eye_points.astype(np.int32))
            cv2.fillPoly(result_image, [hull], (0, 0, 0))
        
        # Blacken lips
        lip_points = []
        for idx in lip_indices:
            point = landmarks.landmark[idx]
            x = int(point.x * w)
            y = int(point.y * h)
            lip_points.append((x, y))
        
        if lip_points:
            lip_points = np.array(lip_points)
            hull = cv2.convexHull(lip_points.astype(np.int32))
            cv2.fillPoly(result_image, [hull], (0, 0, 0))
        
        return result_image
    
    def blacken_eyes_and_lips_opencv(self, image: np.ndarray, face_bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Blacken eyes and mouth using OpenCV with side view detection"""
        result_image = image.copy()
        x, y, w, h = face_bbox
        
        # Detect if it's a side profile by checking face width vs height ratio
        is_side_profile = w < h * 0.8  # Side profiles are typically narrower
        
        if is_side_profile:
            # Side profile masking - position masks on the visible side
            # Calculate eye region - position ON the eye for side view
            eye_y = y + int(h * 0.15)  # Higher up to cover actual eye
            eye_h = int(h * 0.12)  # Height for eye area
            
            # For side profile, mask the visible eye
            if w < h * 0.6:  # Very narrow = side profile
                # Mask the visible eye (usually the one closer to center)
                eye_center_x = x + int(w * 0.6)  # Position towards the visible side
                eye_center_y = eye_y + eye_h // 2
                eye_axes = (int(w * 0.25), int(eye_h * 0.8))  # Larger oval for side view
                cv2.ellipse(result_image, (eye_center_x, eye_center_y), eye_axes, 0, 0, 360, (0, 0, 0), -1)
            else:
                # Mask both eyes for partial side view
                # Left eye
                left_eye_center_x = x + int(w * 0.3)
                left_eye_center_y = eye_y + eye_h // 2
                left_eye_axes = (int(w * 0.2), int(eye_h * 0.8))
                cv2.ellipse(result_image, (left_eye_center_x, left_eye_center_y), left_eye_axes, 0, 0, 360, (0, 0, 0), -1)
                
                # Right eye
                right_eye_center_x = x + int(w * 0.7)
                right_eye_center_y = eye_y + eye_h // 2
                right_eye_axes = (int(w * 0.2), int(eye_h * 0.8))
                cv2.ellipse(result_image, (right_eye_center_x, right_eye_center_y), right_eye_axes, 0, 0, 360, (0, 0, 0), -1)
            
            # Mask mouth for side view - larger and better positioned
            mouth_center_x = x + int(w * 0.5)  # Center of visible face
            mouth_center_y = y + int(h * 0.7)  # Lower position for side view
            mouth_axes = (int(w * 0.4), int(h * 0.18))  # Much larger for side view
            cv2.ellipse(result_image, (mouth_center_x, mouth_center_y), mouth_axes, 0, 0, 360, (0, 0, 0), -1)
            
        else:
            # Front view - use standard positioning
            # Calculate eye region - position to cover actual eyes
            eye_y = y + int(h * 0.2)  # Move up to cover eyes properly
            eye_h = int(h * 0.18)  # Height for eye area
            
            # Left eye (horizontal oval)
            left_eye_center_x = x + int(w * 0.25)  # Center of left eye
            left_eye_center_y = eye_y + eye_h // 2
            left_eye_axes = (int(w * 0.15), int(eye_h * 0.4))  # Horizontal oval
            cv2.ellipse(result_image, (left_eye_center_x, left_eye_center_y), left_eye_axes, 0, 0, 360, (0, 0, 0), -1)
            
            # Right eye (horizontal oval)
            right_eye_center_x = x + int(w * 0.75)  # Center of right eye
            right_eye_center_y = eye_y + eye_h // 2
            right_eye_axes = (int(w * 0.15), int(eye_h * 0.4))  # Horizontal oval
            cv2.ellipse(result_image, (right_eye_center_x, right_eye_center_y), right_eye_axes, 0, 0, 360, (0, 0, 0), -1)
            
            # Mask mouth (horizontal oval) - FIXED for complete coverage
            mouth_center_x = x + w // 2  # Center of mouth
            mouth_center_y = y + int(h * 0.68)  # Better position for complete coverage
            mouth_axes = (int(w * 0.35), int(h * 0.15))  # Much larger oval for complete lip coverage
            cv2.ellipse(result_image, (mouth_center_x, mouth_center_y), mouth_axes, 0, 0, 360, (0, 0, 0), -1)
        
        return result_image
    
    def apply_face_filter(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Apply complete face filter using the best available method.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Dictionary containing original, face-only, and filtered images
        """
        # Detect face
        face_bbox = self.detect_face(image)
        if face_bbox is None:
            return {"error": "No face detected in the image"}
        
        if self.use_mediapipe:
            # Use MediaPipe for more accurate results
            landmarks = self.get_face_landmarks_mediapipe(image)
            if landmarks is None:
                return {"error": "Could not detect facial landmarks"}
            
            # Create face-only mask
            face_only = self.create_face_mask_mediapipe(image, landmarks)
            
            # Apply eye and lip blackening
            filtered_image = self.blacken_eyes_and_lips_mediapipe(face_only, landmarks)
        else:
            # Use OpenCV fallback
            face_only = self.create_face_mask_opencv(image, face_bbox)
            filtered_image = self.blacken_eyes_and_lips_opencv(face_only, face_bbox)
        
        return {
            "original": image,
            "face_only": face_only,
            "filtered": filtered_image,
            "face_bbox": face_bbox,
            "method_used": "MediaPipe" if self.use_mediapipe else "OpenCV"
        }
    
    def capture_multi_angle(self, camera_index: int = 0) -> Dict[str, np.ndarray]:
        """Capture images from multiple angles with face filtering"""
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return {"error": "Could not open camera"}
        
        images = {}
        angles = ["front", "left", "right"]
        
        try:
            for angle in angles:
                print(f"📸 Capturing {angle} angle... Press 'c' to capture, 'q' to quit")
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Display instructions
                    cv2.putText(frame, f"Position for {angle} angle", (50, 50), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.putText(frame, "Press 'c' to capture, 'q' to quit", (50, 100), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    cv2.imshow(f"Camera - {angle}", frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('c'):
                        # Apply face filter to captured image
                        filter_result = self.apply_face_filter(frame)
                        if "error" not in filter_result:
                            images[angle] = filter_result["filtered"]
                            print(f"✅ {angle} angle captured and filtered using {filter_result['method_used']}")
                        else:
                            print(f"❌ Error filtering {angle} angle: {filter_result['error']}")
                        break
                    elif key == ord('q'):
                        break
                
                cv2.destroyWindow(f"Camera - {angle}")
            
            return images
            
        finally:
            cap.release()
            cv2.destroyAllWindows()
    
    def apply_privacy_filter_from_bytes(self, image_bytes: bytes) -> Optional[bytes]:
        """
        Apply privacy filter to image from bytes.
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Filtered image as bytes, or None if error
        """
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return None
            
            # Apply face filter
            filter_result = self.apply_face_filter(image)
            
            if "error" in filter_result:
                return None
            
            # Encode filtered image back to bytes
            _, buffer = cv2.imencode('.jpg', filter_result["filtered"])
            return buffer.tobytes()
            
        except Exception as e:
            print(f"Error applying privacy filter: {e}")
            return None
    
    def apply_privacy_filter(self, image_path: str) -> Optional[str]:
        """
        Apply privacy filter to image file.
        
        Args:
            image_path: Path to input image
            
        Returns:
            Path to filtered image, or None if error
        """
        try:
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                return None
            
            # Apply face filter
            filter_result = self.apply_face_filter(image)
            
            if "error" in filter_result:
                return None
            
            # Save filtered image
            output_path = image_path.replace('.jpg', '_filtered.jpg').replace('.png', '_filtered.png')
            cv2.imwrite(output_path, filter_result["filtered"])
            
            return output_path
            
        except Exception as e:
            print(f"Error applying privacy filter: {e}")
            return None
    
    def process_image_file(self, image_path: str, output_dir: str = "filtered_output") -> Dict:
        """Process a single image file and apply face filter"""
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            return {"error": f"Could not load image from {image_path}"}
        
        # Apply face filter
        filter_result = self.apply_face_filter(image)
        if "error" in filter_result:
            return filter_result
        
        # Save results
        os.makedirs(output_dir, exist_ok=True)
        saved_paths = {}
        
        # Save face-only image
        face_only_path = os.path.join(output_dir, "face_only.jpg")
        cv2.imwrite(face_only_path, filter_result["face_only"])
        saved_paths["face_only"] = face_only_path
        
        # Save filtered image
        filtered_path = os.path.join(output_dir, "filtered.jpg")
        cv2.imwrite(filtered_path, filter_result["filtered"])
        saved_paths["filtered"] = filtered_path
        
        return {
            "success": True,
            "saved_paths": saved_paths,
            "face_bbox": filter_result["face_bbox"],
            "method_used": filter_result["method_used"]
        }
