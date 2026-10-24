const form = document.getElementById("booking-form");

if (form) {
  const dateInput = form.querySelector('input[name="date"]');

  // Выбор слота: показываем итог и включаем кнопку.
  form.addEventListener("change", (event) => {
    const slot = event.target;
    if (!(slot instanceof HTMLInputElement) || slot.name !== "start") return;
    const summary = document.getElementById("booking-summary");
    const submit = document.getElementById("booking-submit");
    const [year, month, day] = dateInput.value.split("-");
    if (summary) summary.textContent = `${day}.${month}.${year}, ${slot.value}–${slot.dataset.end}`;
    if (submit) submit.disabled = false;
  });

  // Защита от двойной отправки.
  form.addEventListener("submit", () => {
    const submit = document.getElementById("booking-submit");
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Бронируем…";
    }
  });
}