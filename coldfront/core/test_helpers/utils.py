"""utility functions for unit and integration testing"""
from bs4 import BeautifulSoup

def page_contains_for_user(test_case, user, url, text):
    """Check that page contains text for user"""
    response = login_and_get_page(test_case.client, user, url)
    test_case.assertContains(response, text)

def page_does_not_contain_for_user(test_case, user, url, text):
    """Check that page contains text for user"""
    response = login_and_get_page(test_case.client, user, url)
    test_case.assertNotContains(response, text)

def collect_all_ids_in_listpage(client, listpage):
    """collect all the ids displayed in the template of a given list view."""
    response = client.get(listpage)
    obj_ids = [o.id for o in response.context_data['object_list']]
    if response.context_data['paginator']:
        num_pages = response.context_data['paginator'].num_pages
        if num_pages > 1:
            pages = range(2, num_pages)
            for page in pages:
                response = client.get(f"{listpage}&page={page}")
                obj_ids.extend([o.id for o in response.context_data['object_list']])
    return obj_ids

def login_and_get_page(client, user, page):
    """force login and return get response for page"""
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    return client.get(page)

def login_and_get_soup(client, user, page):
    """force login and return get response for page"""
    response = login_and_get_page(client, user, page)
    return BeautifulSoup(response.content, 'html.parser')

def test_logged_out_redirect_to_login(test_case, page):
    """
    Confirm that attempting to access page while not logged in triggers a 302
    redirect to a login page.

    Parameters
    ----------
    test_case : must have client.
    page : str
        must begin and end with a slash.
    """
    # log out, in case already logged in
    test_case.client.logout()
    response = test_case.client.get(page)
    test_case.assertRedirects(response, f'/user/login?next={page}')
    # test_case.assertEqual(response.status_code, 302)
    # test_case.assertEqual(response.url, f'/user/login?next={page}')

def test_logged_out_404(test_case, page):
    """
    Confirm that attempting to access page while not logged in triggers a 302
    redirect to a login page.

    Parameters
    ----------
    test_case : must have client.
    page : str
        must begin and end with a slash.
    """
    # log out, in case already logged in
    test_case.client.logout()
    response = test_case.client.get(page)
    test_case.assertEqual(response.status_code, 404)
    # test_case.assertEqual(response.url, f'/user/login?next={page}')


def test_redirect(test_case, page):
    """
    Confirm that attempting to access page in whatever test_case state is given
    produces a redirect.

    Parameters
    ----------
    test_case : must have client.
    page : str
        must begin and end with a slash.

    Returns
    -------
    response.url : string
        the redirected url given.
    """
    response = test_case.client.get(page)
    test_case.assertEqual(response.status_code, 302)
    return response.url


def test_user_cannot_access(test_case, user, page):
    """Confirm that accessing the page as the designated user returns a 403 response code.

    Parameters
    ----------
    test_case : django.test.TestCase.
        must have "client" attr set.
    user : user object
    page : str
        must begin and end with a slash.
    """
    response = login_and_get_page(test_case.client, user, page)
    test_case.assertEqual(response.status_code, 403)

def test_user_can_access(test_case, user, page):
    """Confirm that accessing the page as the designated user returns a 200 response code.

    Parameters
    ----------
    test_case : django.test.TestCase.
        must have "client" attr set.
    user : user object
    page : str
        must begin and end with a slash.
    """
    response = login_and_get_page(test_case.client, user, page)
    test_case.assertEqual(response.status_code, 200)
