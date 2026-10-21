// Copy the functions you need into your existing frontend JavaScript.
// Change API_BASE if the backend runs at another address.

const API_BASE = "http://localhost:8000/api";

async function register(name, email, password) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name, email, password })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Registration failed");
  return data;
}

async function login(email, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Login failed");
  return data;
}

async function getCurrentUser() {
  const response = await fetch(`${API_BASE}/auth/me`, {
    credentials: "include"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Not logged in");
  return data.user;
}

async function logout() {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Logout failed");
  return data;
}

async function loadFAQs(container) {
  const response = await fetch(`${API_BASE}/faqs`);
  if (!response.ok) throw new Error("Could not load FAQs");
  const faqs = await response.json();

  // textContent avoids inserting FAQ content as executable HTML.
  container.replaceChildren();
  for (const faq of faqs) {
    const article = document.createElement("article");
    const question = document.createElement("h3");
    const answer = document.createElement("p");
    question.textContent = faq.question;
    answer.textContent = faq.answer;
    article.append(question, answer);
    container.append(article);
  }
}

// Example:
// login(emailInput.value, passwordInput.value)
//   .then(() => window.location.href = "dashboard.html")
//   .catch(error => alert(error.message));
// loadFAQs(document.getElementById("faq-list"));
