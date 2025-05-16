# import cv2
# import face_recognition
# import pickle
# import numpy as np

# # Load face encodings from the saved .pkl file
# def load_known_faces():
#     with open("face_encodings.pkl", "rb") as f:
#         return pickle.load(f)

# # Test face recognition (check if it detects faces and recognizes them correctly)
# def test_face_recognition():
#     cap = cv2.VideoCapture(0)  # Use the webcam

#     known_faces = load_known_faces()  # Load the saved encodings

#     # Flatten the encodings and create a list of names corresponding to each encoding
#     all_encodings = []
#     all_names = []
#     for name, encodings in known_faces.items():
#         for encoding in encodings:
#             if encoding.shape != (128,):  # Validate encoding shape
#                 print(f"Invalid encoding shape for {name}: {encoding.shape}")
#                 continue
#             all_encodings.append(encoding)
#             all_names.append(name)

#     if not all_encodings:
#         print("No valid face encodings loaded.")
#         return

#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             print("Failed to capture image.")
#             break

#         rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert the image to RGB
#         face_locations = face_recognition.face_locations(rgb_frame)  # Detect faces
#         face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)  # Get face encodings

#         # Check if any face is detected
#         for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
#             if face_encoding.shape != (128,):  # Validate detected encoding
#                 print(f"Invalid detected encoding shape: {face_encoding.shape}")
#                 continue
#             # Compare the face encoding with all known encodings
#             matches = face_recognition.compare_faces(all_encodings, face_encoding, tolerance=0.6)
#             face_distances = face_recognition.face_distance(all_encodings, face_encoding)
            
#             # Debug: Print the matches array to see if it matches
#             print("Matches:", matches)
#             print("Distances:", face_distances)

#             name = "Unknown"
#             if len(face_distances) > 0:
#                 best_match_index = np.argmin(face_distances)
#                 if matches[best_match_index]:
#                     name = all_names[best_match_index]
#                     print(f"Face recognized as: {name} (distance: {face_distances[best_match_index]:.4f})")
#                 else:
#                     print("No matching face found!")

#             # Draw rectangle and label around the face
#             cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
#             cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

#         # Show the video feed
#         cv2.imshow("Face Recognition Test", frame)

#         # Break the loop if 'q' is pressed
#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break

#     cap.release()
#     cv2.destroyAllWindows()

# # Run the face recognition test
# if __name__ == "__main__":
#     test_face_recognition()