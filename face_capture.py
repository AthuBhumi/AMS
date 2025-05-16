# import cv2
# import face_recognition
# import pickle
# import os
# from datetime import datetime

# def capture_and_train_person(name):
#     # Create a directory to store images of the person
#     person_dir = f'images/{name}'
#     if not os.path.exists(person_dir):
#         os.makedirs(person_dir)
#    # Initialize the webcam
#     cap = cv2.VideoCapture(0)

#     print(f"Capturing images of {name}. Please turn your head to different angles. Press 'q' to finish early.")
#     image_count = 0
#     known_face_encodings = []

#     while image_count < 20:  # Capture 20 images
#         ret, frame = cap.read()
#         if not ret:
#             print("Failed to capture image.")
#             break

#         # Convert the image to RGB
#         rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#         face_locations = face_recognition.face_locations(rgb_frame)

#         if len(face_locations) > 0:  # If face detected
#             face_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
#             if face_encoding.shape != (128,):  # Validate encoding shape
#                 print(f"Invalid encoding shape for frame {image_count + 1}: {face_encoding.shape}")
#                 continue
#             known_face_encodings.append(face_encoding)
#             image_count += 1
#             image_path = os.path.join(person_dir, f'{name}_{image_count}.jpg')
#             cv2.imwrite(image_path, frame)
#             print(f"Captured {image_count} images of {name}")

#             # Show the frame with the detected face
#             for (top, right, bottom, left) in face_locations:
#                 cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

#         cv2.imshow("Capturing Images", frame)

#         # Press 'q' to quit early
#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break

#     cap.release()
#     cv2.destroyAllWindows()

#     # Save the face encodings to a .pkl file
#     if not known_face_encodings:
#         print("No valid face encodings captured.")
#         return

#     if os.path.exists("face_encodings.pkl"):
#         with open("face_encodings.pkl", "rb") as f:
#             all_face_encodings = pickle.load(f)
#     else:
#         all_face_encodings = {}

#     # Add the new person's encoding
#     all_face_encodings[name] = known_face_encodings

#     # Save the updated encodings to the file
#     with open("face_encodings.pkl", "wb") as f:
#         pickle.dump(all_face_encodings, f)

#     print(f"{name} registered successfully with {len(known_face_encodings)} images!")

# # Example usage: Register a new person
# if __name__ == "__main__":
#     capture_and_train_person("Aishwarya")