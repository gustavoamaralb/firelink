// Copy to config.js (kept out of Git), next to index.html, and fill it in.
// Between the braces use plain JSON (double quotes, no comments): the API reads this file too.
//   people:     name -> Portuguese gender ending for "bem-vindo"/"bem-vinda" ("o" or "a")
//   birthdays:  name -> "MM-DD" (pets welcome, e.g. "Akali")
//   mothersDay: who gets congratulated on Mother's Day
//   mothersDayLetter: optional letter shown to that person on Mother's Day
window.FIRELINK = {
  "people": { "Fulano": "o", "Fulana": "a" },
  "birthdays": { "Fulano": "01-31", "Fulana": "07-15" },
  "mothersDay": ["Fulana"],
  "mothersDayLetter": { "Fulana": "Write your message here. Fulano." }
};
