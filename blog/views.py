from urllib import request

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django.core.mail import send_mail
from django.db.models import Count

from .models import Post
from django.contrib.postgres.search import SearchVector, TrigramSimilarity
from .forms import CommentForm, EmailPostForm, SearchForm
from taggit.models import Tag
from django.contrib.postgres.search import (
 SearchVector,
 SearchQuery,
 SearchRank
)



# -------------------------------
# Class-based post list view
# -------------------------------
class PostListView(ListView):
    """
    Alternative post list view using class-based view
    """
    queryset = Post.published.all()
    context_object_name = 'posts'
    paginate_by = 3
    template_name = 'blog/post/list.html'


# -------------------------------
# Function-based post list view
# -------------------------------
def post_list(request, tag_slug=None):
    post_list = Post.published.all()
    tag = None
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        post_list = post_list.filter(tags__in=[tag])

    paginator = Paginator(post_list, 3)
    page_number = request.GET.get('page')

    try:
        posts = paginator.page(page_number)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        posts = paginator.page(paginator.num_pages)

    return render(request, 'blog/post/list.html', {
        'posts': posts,
        'tag': tag
    })


# -------------------------------
# Post detail view with comments and similar posts
# -------------------------------
def post_detail(request, year, month, day, slug):
    post = get_object_or_404(
        Post,
        status=Post.Status.PUBLISHED,
        slug=slug,
        publish__year=year,
        publish__month=month,
        publish__day=day
    )

    # List of active comments
    comments = post.comments.filter(active=True)

    # Comment form
    form = CommentForm()

    # ------------------------
    # Similar posts (by tags)
    # ------------------------
    post_tags_ids = post.tags.values_list('id', flat=True)
    similar_posts = Post.published.filter(tags__in=post_tags_ids) \
                                  .exclude(id=post.id) \
                                  .annotate(same_tags=Count('tags')) \
                                  .order_by('-same_tags', '-publish')[:4]

    return render(request, 'blog/post/detail.html', {
        'post': post,
        'comments': comments,
        'form': form,
        'similar_posts': similar_posts
    })


# -------------------------------
# Share post via email
# -------------------------------
def post_share(request, post_id):
    post = get_object_or_404(
        Post,
        id=post_id,
        status=Post.Status.PUBLISHED
    )

    sent = False

    if request.method == 'POST':
        form = EmailPostForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            post_url = request.build_absolute_uri(post.get_absolute_url())
            subject = f"{cd['name']} ({cd['email']}) recommends you read {post.title}"
            message = f"Read {post.title} at {post_url}\n\n{cd['name']}'s comments: {cd['comments']}"
            send_mail(subject, message, None, [cd['to']])
            sent = True
    else:
        form = EmailPostForm()

    return render(request, 'blog/post/share.html', {
        'post': post,
        'form': form,
        'sent': sent
    })


# -------------------------------
# Post comment view
# -------------------------------
@require_POST
def post_comment(request, post_id):
    post = get_object_or_404(
        Post,
        id=post_id,
        status=Post.Status.PUBLISHED
    )

    comment = None
    form = CommentForm(data=request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.save()

    # After posting, render comment template (partial)
    return render(request, 'blog/post/comment.html', {
        'post': post,
        'form': form,
        'comment': comment
    })
def post_search(request):
    form = SearchForm()
    query = None
    results = []

    if 'query' in request.GET:
        form = SearchForm(request.GET)
        if form.is_valid():
            query = form.cleaned_data['query']

            # Create search vector on title and body
            search_vector = SearchVector('title', weight='A') + SearchVector('body', weight='B') + SearchVector('tags__name', weight='C')

            # Search query
            search_query = SearchQuery(query , config='spanish')

            # Search results
            results = (
                Post.published
                .annotate(similarity=TrigramSimilarity('title', query))
                .filter(similarity__gt=0.1)  # optional: only posts with some rank
                .order_by('-similarity')
            )

            # Include tag filtering separately
            tag_matches = Post.published.filter(tags__name__icontains=query)

            # Combine query results and tag results
            results = (results | tag_matches).distinct()

    return render(
        request,
        'blog/post/search.html',
        {
            'form': form,
            'query': query,
            'results': results
        }
    )
