# Nagrik.ai - Zero-Trust Civic Reporting Portal

Nagrik.ai is an AI-powered civic infrastructure reporting platform designed to eliminate manual triaging of public grievances. It utilizes computer vision to automatically detect, classify, and route civic issues (such as potholes, water leaks, waste management, sewage and open wiring) directly to the relevant municipal departments.

## 🚀 Key Features

*   **AI Auto-Classification:** Integrates with Gemini 2.5 Flash to analyze user-uploaded images and intelligently classify the problem category (PWD, Jal Nigam, UPPCL, etc.).
*   **Zero-Spam Deduplication:** Implements Haversine formula-based geofencing to detect multiple reports of the exact same issue within a 50-meter radius, merging them into a single high-priority ticket.
*   **Dual-Image Resolution Audit:** Enforces accountability by requiring officers to upload 'After' repair photos, which are then evaluated by AI against the original 'Before' image to generate a confidence/match score.
*   **Smart Routing & Fallback:** Strictly isolates departmental access. Includes smart fallback mechanisms to ensure the portal remains robust even during API quota exhaustion.
*   **Live Radar:** A transparent, Leaflet.js-powered public mapping system displaying real-time civic issues across specific coordinates.

## 🔄 System Architecture & Data Flow

### 1. Citizen Reporting & AI Triaging
* **Report Initiation:** A citizen uploads an image of a civic issue via the portal. The backend captures the image, compresses it, and securely extracts live GPS telemetry.
* **AI Processing:** The image is passed to the AI model, which automatically categorizes the issue(e.g., Electricity, Water, Pothole, Waste) and generates bilingual descriptions.
* **Ticket Generation:** Upon successful submission, a unique tracking ID (e.g., NAGRIK-XXXX) is generated and provided to the citizen to track that issue.

### 2. Departmental Isolation & Officer Dashboard
* **Role-Based Authentication:** Officers log into the secure dashboard using department-specific credentials (e.g., PWD, Jal Nigam). 
* **Data Isolation:** The Flask backend queries Firebase Firestore to serve only the issues relevant to the logged-in officer's specific department category. This enforces strict jurisdiction and ensures zero cross-department data pollution.

### 3. Automated Resolution & Audit
* **Status Updates:** Officers can update the status of a ticket to 'In Progress' or 'Resolved'.
* **Visual Verification:** To mark an issue as 'Resolved', the officer must upload an 'After' photograph of the repaired site.
* **AI Confidence Scoring:** The backend invokes the AI model to visually compare the citizen's 'Before' image with the officer's 'After' image. It generates a resolution confidence score (e.g., 95% Match) which is securely logged in the database.

### 4. Citizen Tracking & Transparency
* **Real-Time Tracking:** Citizens use their unique Ticket ID on the 'Track Status' tab to view real-time administrative updates.
* **Visual Evidence display:** Once an issue is resolved, the portal displays both the 'Before' and 'After' images side-by-side, along with the AI-generated verification score, establishing complete administrative transparency.

## 🛠️ Tech Stack

*   **Backend:** Python, Flask
*   **Database & Authentication:** Firebase Firestore, Firebase Admin SDK
*   **Artificial Intelligence:** Google GenAI SDK (Gemini 2.5 Flash)
*   **Frontend:** HTML5, Tailwind CSS, JavaScript (ES6)
*   **Geospatial Mapping:** Leaflet.js

## ⚙️ Local Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
   cd NAGRIK_AI