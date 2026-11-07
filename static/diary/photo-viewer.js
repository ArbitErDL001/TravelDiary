const photoViewer = document.querySelector("[data-profile-image-viewer]");
const photoViewerImage = photoViewer?.querySelector("[data-profile-image-viewer-image]");
const photoDownloadLink = photoViewer?.querySelector("[data-profile-image-download]");

const closePhotoViewer = () => photoViewer?.close();
photoViewer?.querySelector("[data-profile-image-close]")?.addEventListener("click", closePhotoViewer);
photoViewer?.addEventListener("cancel", (event) => {
  event.preventDefault();
  closePhotoViewer();
});
photoViewer?.addEventListener("click", (event) => {
  if (event.target === photoViewer) closePhotoViewer();
});
document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const trigger = target?.closest("[data-fullscreen-photo]");
  if (!trigger) return;
  const image = trigger.matches("img") ? trigger : trigger.querySelector("img");
  if (!image) return;
  const imageUrl = new URL(image.currentSrc || image.src, window.location.href);
  photoViewerImage.src = imageUrl.href;
  photoViewerImage.alt = image.alt;
  photoDownloadLink.href = imageUrl.href;
  photoDownloadLink.download = decodeURIComponent(imageUrl.pathname.split("/").pop()) || "travel-photo";
  photoViewer.showModal();
  photoViewer.querySelector("[data-profile-image-close]").focus();
});
document.addEventListener("keydown", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const trigger = target?.closest("[data-fullscreen-photo]");
  if (trigger && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    trigger.click();
  }
});
