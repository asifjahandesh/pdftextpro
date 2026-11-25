import "./globals.css";

export const metadata = {
  title: "PDFText Pro — Multilingual PDF & OCR Extraction",
  description: "Extract text from digital and scanned multilingual PDFs.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
