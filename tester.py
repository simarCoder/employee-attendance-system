import sqlite3

from backend.app import app
from backend.utils.security import decrypt_password, encrypt_password
from backend.services.settings import add_system_user


app.secret_key = "TEST_SECRET_KEY_ONLY"


DB = "db/attendance.db"


def get_test_users():
    conn = sqlite3.connect(DB)

    rows = conn.execute("""
        SELECT user_id, username, password_hash, role
        FROM users
        ORDER BY user_id
    """).fetchall()

    conn.close()

    users = {}

    for user_id, username, encrypted_password, role in rows:
        users[role] = {
            "id": user_id,
            "username": username,
            "password": decrypt_password(encrypted_password),
        }

    # The permission tests require a normal user.
    # Create a temporary one if the database does not have one.
    if "user" not in users:
        test_username = "__permission_test_user__"
        test_password = "__permission_test_password__"

        try:
            add_system_user(
                test_username,
                test_password,
                "user"
            )
        except Exception:
            # The account may already exist.
            pass

        conn = sqlite3.connect(DB)

        row = conn.execute("""
            SELECT user_id, username, password_hash, role
            FROM users
            WHERE username = ?
        """, (test_username,)).fetchone()

        conn.close()

        if row:
            user_id, username, encrypted_password, role = row

            users[role] = {
                "id": user_id,
                "username": username,
                "password": decrypt_password(encrypted_password),
            }

    return users


users = get_test_users()

print("\n=== USERS ===")

for role, user in users.items():
    print(
        f"{role:6} -> "
        f"{user['username']} "
        f"(ID {user['id']})"
    )


client = app.test_client()

def login(client, user):
    return client.post(
        "/login",
        json={
            "username": user["username"],
            "password": user["password"],
        },
    )

def restore_password(user_id, original_password):
    conn = sqlite3.connect(DB)

    conn.execute("""
        UPDATE users
        SET password_hash = ?
        WHERE user_id = ?
    """, (
        # We cannot store plaintext directly.
        # Use the application's password encryption function instead.
        encrypt_password(original_password),
        user_id
    ))

    conn.commit()
    conn.close()


def check(name, response, expected):
    if response.status_code == expected:
        print(f"PASS  {name}")
        return True

    print(
        f"FAIL  {name} "
        f"(expected {expected}, got {response.status_code})"
    )
    return False


passed = 0
failed = 0


# =========================================================
# LOGIN
# =========================================================

print("\n=== LOGIN TEST ===")

for role in ("head", "admin", "user"):

    client = app.test_client()

    response = login(client, users[role])

    if check(
        f"{role} login",
        response,
        200
    ):
        passed += 1
    else:
        failed += 1


# =========================================================
# /users ACCESS
# =========================================================

print("\n=== USER MANAGEMENT ACCESS ===")


def test_users_access(role, expected):

    global passed, failed

    client = app.test_client()

    response = login(client, users[role])
    if response.status_code != 200:
        print(
            f"FAIL  {role} login before /users "
            f"({response.status_code})"
        )
        failed += 1
        return

    response = client.get("/users")

    if check(
        f"{role} -> GET /users",
        response,
        expected
    ):
        passed += 1
    else:
        failed += 1


test_users_access("head", 200)
test_users_access("admin", 200)
test_users_access("user", 403)


# =========================================================
# PASSWORD PERMISSIONS
# =========================================================

print("\n=== PASSWORD PERMISSIONS ===")


def get_password_snapshot():
    conn = sqlite3.connect(DB)

    rows = conn.execute("""
        SELECT user_id, password_hash
        FROM users
    """).fetchall()

    conn.close()

    return {
        user_id: password_hash
        for user_id, password_hash in rows
    }


def restore_password_snapshot(snapshot):
    conn = sqlite3.connect(DB)

    for user_id, password_hash in snapshot.items():
        conn.execute("""
            UPDATE users
            SET password_hash = ?
            WHERE user_id = ?
        """, (password_hash, user_id))

    conn.commit()
    conn.close()

    # Refresh users dictionary because successful password
    # tests temporarily modify the database password.
    global users
    users = get_test_users()


def test_password(actor_role, target_role, expected):
    global passed, failed

    actor = users[actor_role]
    target = users[target_role]

    client = app.test_client()

    response = login(client, actor)
    
    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before password test"
        )
        failed += 1
        return

    original_password = target["password"]

    response = client.post(
        "/users/password",
        json={
            "user_id": target["id"],
            "password": "__PERMISSION_TEST__",
        },
    )

    if response.status_code == expected:
        print(
            f"PASS  {actor_role} -> "
            f"change {target_role} password"
        )
        passed += 1
    else:
        print(
            f"FAIL  {actor_role} -> "
            f"change {target_role} password "
            f"(expected {expected}, got {response.status_code})"
        )
        failed += 1

    # Restore original password after every successful mutation.
    if response.status_code == 200:
        restore_password(
            target["id"],
            original_password
        )


test_password("user", "user", 200)
test_password("user", "admin", 403)
test_password("user", "head", 403)

test_password("admin", "user", 200)
test_password("admin", "admin", 200)
test_password("admin", "head", 403)

test_password("head", "user", 200)
test_password("head", "admin", 200)
test_password("head", "head", 200)
# =========================================================
# CREATE ACCOUNT PERMISSIONS
# =========================================================

print("\n=== CREATE ACCOUNT PERMISSIONS ===")


def test_create(actor_role, target_role, expected):
    global passed, failed

    client = app.test_client()

    response = login(client, users[actor_role])

    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before create test"
        )
        failed += 1
        return

    username = (
        f"__permission_test_"
        f"{actor_role}_"
        f"{target_role}__"
    )

    response = client.post(
        "/users/add",
        json={
            "username": username,
            "password": "__PERMISSION_TEST_PASSWORD__",
            "role": target_role,
        },
    )

    if response.status_code == expected:
        print(
            f"PASS  {actor_role} -> "
            f"create {target_role}"
        )
        passed += 1
    else:
        print(
            f"FAIL  {actor_role} -> "
            f"create {target_role} "
            f"(expected {expected}, got {response.status_code})"
        )
        failed += 1

    # Always remove temporary account.
    conn = sqlite3.connect(DB)

    conn.execute("""
        DELETE FROM users
        WHERE username = ?
    """, (username,))

    conn.commit()
    conn.close()


# User
test_create("user", "user", 403)
test_create("user", "admin", 403)
test_create("user", "head", 403)

# Admin
test_create("admin", "user", 200)
test_create("admin", "admin", 403)
test_create("admin", "head", 403)

# Developer
test_create("head", "user", 200)
test_create("head", "admin", 200)
test_create("head", "head", 200)

# =========================================================
# DELETE PERMISSIONS
# =========================================================

print("\n=== DELETE PERMISSIONS ===")


def create_delete_target(role):
    username = f"__delete_test_{role}__"

    try:
        add_system_user(
            username,
            "__DELETE_TEST_PASSWORD__",
            role
        )
    except Exception:
        pass

    conn = sqlite3.connect(DB)

    row = conn.execute("""
        SELECT user_id
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    conn.close()

    return username, row[0] if row else None


def test_delete(actor_role, target_role, expected):
    global passed, failed

    username, target_id = create_delete_target(target_role)

    if not target_id:
        print(
            f"FAIL  Could not create "
            f"temporary {target_role} account"
        )
        failed += 1
        return

    client = app.test_client()

    response = login(client, users[actor_role])

    if response.status_code != 200:
        print(
            f"FAIL  {actor_role} login "
            f"before delete test"
        )
        failed += 1

        conn = sqlite3.connect(DB)
        conn.execute(
            "DELETE FROM users WHERE user_id = ?",
            (target_id,)
        )
        conn.commit()
        conn.close()

        return

    response = client.post(
        "/users/delete",
        json={
            "user_id": target_id,
        },
    )

    if response.status_code == expected:
        print(
            f"PASS  {actor_role} -> "
            f"delete {target_role}"
        )
        passed += 1
    else:
        print(
            f"FAIL  {actor_role} -> "
            f"delete {target_role} "
            f"(expected {expected}, got {response.status_code})"
        )
        failed += 1

    # Cleanup if deletion was forbidden.
    conn = sqlite3.connect(DB)

    conn.execute("""
        DELETE FROM users
        WHERE user_id = ?
    """, (target_id,))

    conn.commit()
    conn.close()


# User
test_delete("user", "user", 403)
test_delete("user", "admin", 403)
test_delete("user", "head", 403)

# Admin
test_delete("admin", "user", 200)
test_delete("admin", "admin", 403)
test_delete("admin", "head", 403)

# Developer
test_delete("head", "user", 200)
test_delete("head", "admin", 200)
test_delete("head", "head", 200)


# =========================================================
# RESULT
# =========================================================

# # Clean temporary permission-test user
# conn = sqlite3.connect(DB)

# conn.execute("""
#     DELETE FROM users
#     WHERE username = ?
# """, ("__permission_test_user__",))

# conn.commit()
# conn.close()

print("\n" + "=" * 55)
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
print("=" * 55)



if failed == 0:
    print("ALL PERMISSION TESTS PASSED")
else:
    print("PERMISSION TESTS FAILED")