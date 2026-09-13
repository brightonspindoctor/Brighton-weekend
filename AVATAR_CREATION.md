# Avatar creation process

When a new Brighton Weekend avatar is created, the **selected image is the image that goes into the app**.

1. Generate the avatar artwork.
2. If multiple images are generated, choose the final image with the user.
3. Use that exact selected image file as the avatar asset. Do **not** redraw it, replace it with an SVG, create a placeholder, or regenerate a similar version.
4. Put the selected raster image in `profile-icons/` and register that exact filename with `scripts/add-avatar.mjs` / the **Add avatar** GitHub Action.
5. The registration process records a SHA-256 fingerprint of the selected file in `profile-icons/avatar-manifest.json`.
6. Validation checks the fingerprint on every avatar registration, so an artwork change is detected instead of silently substituting a different image.

Supported avatar artwork formats are PNG, JPG/JPEG and WebP. SVG placeholders are intentionally rejected by the creation process.

**Rule:** selection is approval. Once the user selects an image, that exact artwork is the source of truth for the app avatar.
