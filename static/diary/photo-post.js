(() => {
  const dialog = document.querySelector("[data-profile-post-dialog]");
  const dialogContent = dialog?.querySelector("[data-profile-post-dialog-content]");
  const detailContent = document.querySelector("[data-photo-post-detail]");
  const content = dialogContent || detailContent;
  if (!content) return;

  const root = dialog || detailContent;

  function getCsrfToken() {
    const cookieToken = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1];
    const formToken = content.querySelector("[name=csrfmiddlewaretoken]")?.value;
    return decodeURIComponent(cookieToken || formToken || "");
  }

  function setStatus(message) {
    const status = content.querySelector("[data-post-status]");
    if (status) status.textContent = message;
  }

  function savedKey(photoId) {
    return `roam-saved-${photoId}`;
  }

  function syncSaveButtons(container) {
    container.querySelectorAll("[data-profile-post-save]").forEach((button) => {
      try {
        const saved = localStorage.getItem(savedKey(button.dataset.photoId)) === "true";
        button.classList.toggle("saved", saved);
        button.setAttribute("aria-pressed", String(saved));
        button.setAttribute("aria-label", saved ? "Remove saved post" : "Save post");
        button.querySelector("[data-save-label]").textContent = saved ? "Saved" : "Save";
      } catch {
        button.disabled = true;
        button.setAttribute("aria-label", "Saving posts is unavailable in this browser");
      }
    });
  }

  function createCommentLikeButton(comment) {
    const button = document.createElement("button");
    button.className = "profile-post-comment-like";
    button.type = "button";
    button.dataset.commentLikeUrl = `/comments/${comment.id}/like/`;
    button.setAttribute("aria-pressed", "false");
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#heart");
    icon.append(use);
    const count = document.createElement("span");
    count.textContent = comment.like_count || 0;
    button.append(icon, count);
    return button;
  }

  function createComment(comment, isReply) {
    const article = document.createElement("article");
    article.className = `profile-post-comment${isReply ? " profile-post-reply" : ""}`;
    article.dataset.commentId = comment.id;
    const author = document.createElement("strong");
    author.textContent = comment.author_name || "Traveler";
    const body = document.createElement("p");
    body.textContent = comment.body;
    article.append(author, body);
    if (content.querySelector("[data-profile-post]")?.dataset.authenticated === "true") {
      const actions = document.createElement("div");
      actions.className = "profile-post-comment-actions";
      actions.append(createCommentLikeButton(comment));
      if (!isReply) {
        const reply = document.createElement("button");
        reply.className = "profile-post-reply-button";
        reply.type = "button";
        reply.dataset.profilePostReply = "";
        reply.dataset.commentId = comment.id;
        reply.dataset.commentAuthor = comment.author_name || "Traveler";
        reply.textContent = "Reply";
        actions.append(reply);
      }
      article.append(actions);
    }
    return article;
  }

  function initializePost(container) {
    syncSaveButtons(container);
  }

  document.querySelectorAll("[data-profile-post-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const template = button.closest(".profile-photo").querySelector(".profile-post-template");
      content.replaceChildren(template.content.cloneNode(true));
      initializePost(content);
      dialog.showModal();
    });
  });

  initializePost(content);

  dialog?.querySelector("[data-profile-post-close]")?.addEventListener("click", () => dialog.close());
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  root.addEventListener("click", async (event) => {
    const saveButton = event.target.closest("[data-profile-post-save]");
    if (saveButton) {
      try {
        const saved = localStorage.getItem(savedKey(saveButton.dataset.photoId)) === "true";
        localStorage.setItem(savedKey(saveButton.dataset.photoId), String(!saved));
        syncSaveButtons(content);
        setStatus(saved ? "Removed from saved memories." : "Saved to your memories.");
      } catch {
        setStatus("Could not save this post in this browser.");
      }
      return;
    }

    const shareButton = event.target.closest("[data-profile-post-share]");
    if (shareButton) {
      const url = new URL(`/photos/${shareButton.dataset.photoId}/`, window.location.origin).href;
      try {
        if (navigator.share) {
          await navigator.share({title: "Travel memory", url});
          setStatus("Post shared.");
        } else if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(url);
          setStatus("Post link copied.");
        } else {
          throw new Error("Sharing is not available in this browser.");
        }
      } catch (error) {
        if (error.name !== "AbortError") setStatus(error.message || "Could not share this post.");
      }
      return;
    }

    const commentFocusButton = event.target.closest("[data-profile-post-comment-focus]");
    if (commentFocusButton) {
      content.querySelector("[data-profile-post-comment-form] textarea")?.focus();
      return;
    }

    const cancelReplyButton = event.target.closest("[data-profile-post-cancel-reply]");
    if (cancelReplyButton) {
      const form = cancelReplyButton.closest("form");
      form.elements.parent.value = "";
      form.querySelector("[data-profile-post-replying]").hidden = true;
      return;
    }

    const replyButton = event.target.closest("[data-profile-post-reply]");
    if (replyButton) {
      const form = content.querySelector("[data-profile-post-comment-form]");
      form.elements.parent.value = replyButton.dataset.commentId;
      form.querySelector("[data-profile-post-replying] strong").textContent = replyButton.dataset.commentAuthor;
      form.querySelector("[data-profile-post-replying]").hidden = false;
      form.elements.body.focus();
      return;
    }

    const commentLikeButton = event.target.closest("[data-comment-like-url]");
    if (commentLikeButton) {
      commentLikeButton.disabled = true;
      try {
        const response = await fetch(commentLikeButton.dataset.commentLikeUrl, {
          method: "POST",
          headers: {"X-CSRFToken": getCsrfToken(), "X-Requested-With": "XMLHttpRequest"},
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error(`Could not update comment like (${response.status}).`);
        const result = await response.json();
        commentLikeButton.querySelector("span").textContent = result.like_count;
        commentLikeButton.setAttribute("aria-pressed", String(result.liked));
        commentLikeButton.classList.toggle("liked", result.liked);
      } catch (error) {
        setStatus(error.message || "Could not update comment like.");
      } finally {
        commentLikeButton.disabled = false;
      }
      return;
    }

    const likeButton = event.target.closest("[data-profile-post-like]");
    if (!likeButton) return;
    likeButton.disabled = true;
    try {
      const response = await fetch(`/api/photos/${likeButton.dataset.photoId}/like/`, {
        method: "POST",
        headers: {"X-CSRFToken": getCsrfToken()},
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`Could not update this like (${response.status}).`);
      const result = await response.json();
      likeButton.querySelector("[data-like-count]").textContent = result.like_count;
      likeButton.setAttribute("aria-pressed", String(result.liked));
      likeButton.classList.toggle("liked", result.liked);
      setStatus(result.liked ? "Added to your likes." : "Like removed.");
    } catch (error) {
      setStatus(error.message || "Could not update this like.");
    } finally {
      likeButton.disabled = false;
    }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-profile-post-comment-form]");
    if (!form) return;
    event.preventDefault();
    const body = form.elements.body.value.trim();
    if (!body) return;
    const post = content.querySelector("[data-profile-post]");
    const parentId = form.elements.parent.value;
    const submitButton = form.querySelector("button[type=submit]");
    submitButton.disabled = true;
    try {
      const response = await fetch("/api/photo-comments/", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": getCsrfToken()},
        credentials: "same-origin",
        body: JSON.stringify({
          photo: post.dataset.photoId,
          body,
          parent: parentId || null,
        }),
      });
      if (!response.ok) throw new Error(`Could not post your comment (${response.status}).`);
      const comment = await response.json();
      const comments = content.querySelector("[data-profile-post-comments]");
      comments.querySelector(".profile-post-empty")?.remove();
      if (parentId) {
        const thread = comments.querySelector(`[data-comment-thread-id="${parentId}"]`);
        thread?.append(createComment(comment, true));
      } else {
        const thread = document.createElement("div");
        thread.className = "profile-post-comment-thread";
        thread.dataset.commentThreadId = comment.id;
        thread.append(createComment(comment, false));
        comments.append(thread);
      }
      const count = content.querySelector("[data-comment-count]");
      const nextCount = Number(count.textContent) + 1;
      count.textContent = nextCount;
      content.querySelector("[data-profile-post-comment-focus]")
        ?.setAttribute("aria-label", `Jump to comments, ${nextCount} comments`);
      form.reset();
      form.querySelector("[data-profile-post-replying]").hidden = true;
      setStatus(parentId ? "Reply posted." : "Comment posted.");
    } catch (error) {
      setStatus(error.message || "Could not post your comment.");
    } finally {
      submitButton.disabled = false;
    }
  });
})();
