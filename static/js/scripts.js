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
    const formData = {
        name: document.getElementById('name').value,
        club: document.getElementById('club').value,
        coach: document.getElementById('coach').value,
        discipline: document.getElementById('discipline').value,
        personal_best: parseInt(document.getElementById('personal_best').value, 10)
    };

    try {
        const response = await fetch('/profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData),
        });

        if (response.ok) {
            alert('Profile updated successfully!');
            loadProfile();
            document.getElementById('profile-form').style.display = 'none';
        } else {
            const errorData = await response.json();
            alert(`Error updating profile: ${JSON.stringify(errorData.detail)}`);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('There was an error updating your profile. Please try again.');
    }
});

loadProfile();
