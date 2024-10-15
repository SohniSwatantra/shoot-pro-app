async function loadProfile() {
    const response = await fetch('/profile');
    const profile = await response.json();
    displayProfile(profile);
}

function displayProfile(profile) {
    const profileDisplay = document.getElementById('profile-display');
    profileDisplay.innerHTML = `
        <p><strong>Name:</strong> ${profile.name}</p>
        <p><strong>Shooting Club:</strong> ${profile.club}</p>
        <p><strong>Coach:</strong> ${profile.coach}</p>
        <p><strong>Discipline:</strong> ${profile.discipline}</p>
        <p><strong>Personal Best:</strong> ${profile.personal_best}</p>
    `;
}

function editProfile() {
    const form = document.getElementById('profile-form');
    form.style.display = 'block';
}

document.getElementById('profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const profile = Object.fromEntries(formData);

    const response = await fetch('/profile', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(profile),
    });

    if (response.ok) {
        loadProfile();
        document.getElementById('profile-form').style.display = 'none';
    } else {
        alert('Error updating profile');
    }
});

loadProfile();
