# Creating a GitHub Repository, Setting Up Personal Access Token, and Syncing Code

Follow these steps to create a GitHub repository, set up a personal access token, and sync your code:

1. Go to https://github.com and sign in to your account.
2. Click on your profile picture in the top right corner and select "Settings".
3. In the left sidebar, click on "Developer settings".
4. Click on "Personal access tokens" and then "Tokens (classic)".
5. Click "Generate new token" and select "Generate new token (classic)".
6. Give your token a descriptive name, e.g., "ShootProApp".
7. Select the following scopes: "repo", "workflow", "write:packages".
8. Click "Generate token" at the bottom of the page.
9. Copy the generated token immediately. You won't be able to see it again!

Now, let's create the repository and push the code:

10. Go back to the GitHub homepage and click on the "+" icon in the top right corner.
11. Select "New repository".
12. Name your repository "shoot-pro-app".
13. Set the repository to Public.
14. Do not initialize the repository with a README, .gitignore, or license.
15. Click "Create repository".

After creating the repository and generating the token:

16. In your local terminal, run the following command to update the remote URL with your personal access token:
    ```
    git remote set-url origin https://YOUR_PERSONAL_ACCESS_TOKEN@github.com/YOUR_GITHUB_USERNAME/shoot-pro-app.git
    ```
    Replace `YOUR_PERSONAL_ACCESS_TOKEN` with the token you just generated, and `YOUR_GITHUB_USERNAME` with your actual GitHub username.

17. Verify the remote URL (it should now include your token):
    ```
    git remote -v
    ```

18. Push your code to the new repository:
    ```
    git push -u origin main
    ```

19. Refresh your GitHub repository page to see your code synced to GitHub.

After you've completed these steps, your local code will be synced with the new GitHub repository.

Note: Keep your personal access token secure and do not share it with others. If you accidentally expose your token, immediately revoke it on GitHub and generate a new one.
