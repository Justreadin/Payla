// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-auth.js";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCa9qT--u3f2moMgDiCXj2RnLSDTVvoZZs",
  authDomain: "payla-elite.firebaseapp.com",
  projectId: "payla-elite",
  storageBucket: "payla-elite.firebasestorage.app",
  messagingSenderId: "956501713797",
  appId: "1:956501713797:web:e5dcce5cfe11c0d0de1aec"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase Auth
export const auth = getAuth(app);
