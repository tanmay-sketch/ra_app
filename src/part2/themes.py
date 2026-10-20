"""Reviewed disclosure phrases; avoid broad legal, voting and compensation terms."""

PHRASES = {
    'Integrity': (
        'ethics', 'ethical conduct', 'ethical behavior', 'ethical behaviour',
        'business integrity', 'code of conduct', 'code of ethics', 'business conduct',
        'anti-corruption', 'anti-bribery', 'whistleblower', 'whistleblowing',
        'compliance program', 'compliance programs', 'speak up', 'human rights',
    ),
    'Innovation': (
        'innovation', 'innovations', 'innovative', 'innovating', 'research and development',
        'R&D', 'scientific discovery', 'new technologies', 'new technology',
        'product development', 'technological advances', 'digital transformation',
    ),
    # Product quality phrases avoid treating financial audit controls as a value.
    'Quality': (
        'product quality', 'service quality', 'quality of our products',
        'quality of our services', 'product quality standards', 'product quality assurance',
        'product quality control', 'product reliability', 'service reliability',
        'manufacturing excellence', 'high-quality products', 'high quality products',
    ),
    'Safety': (
        'safety', 'cybersecurity', 'cyber security', 'data security', 'information security',
        'data privacy', 'privacy', 'occupational health', 'workplace injuries',
        'workplace injury', 'injury prevention', 'accident prevention',
    ),
    'Customers': (
        'our customers', 'our clients', 'our users', 'patients', 'patient care',
        'patient outcomes', 'patient access', 'customer experience', 'customer needs',
        'customer satisfaction', 'customer service', 'client experience',
        'client satisfaction', 'consumer needs', 'customer relationships',
    ),
    'Employees': (
        'our employees', 'workforce', 'human capital', 'employee benefits',
        'employee development', 'employee engagement', 'employee wellbeing',
        'employee well-being', 'employee health', 'employee retention',
        'employee compensation', 'working conditions', 'talent development',
        'career development', 'professional development', 'pay equity',
    ),
    'Inclusion': (
        'diversity', 'inclusion', 'inclusive workplace', 'inclusive culture',
        'diverse workforce', 'racial equity', 'racial justice', 'gender equality',
        'gender equity', 'equal opportunity', 'accessibility', 'disabilities',
        'underrepresented', 'under-represented', 'non-discrimination',
    ),
    # Specific climate phrases avoid unrelated uses such as "economic climate".
    'Environment': (
        'environmental', 'emissions', 'carbon', 'greenhouse gas',
        'climate change', 'climate risk', 'climate risks', 'climate-related',
        'climate related', 'climate strategy', 'climate goals', 'climate science',
        'climate policy', 'climate policies', 'climate solutions', 'climate action',
        'climate commitments', 'climate report', 'climate transition',
        'renewable energy', 'energy efficiency', 'natural resources',
        'water conservation', 'biodiversity', 'zero waste', 'recycling',
        'recycled', 'decarbonization', 'environmental sustainability',
    ),
    'Community': (
        'our communities', 'local communities', 'community investment',
        'community engagement', 'community development', 'community service',
        'community support', 'philanthropy', 'philanthropic', 'charitable',
        'charities', 'volunteering', 'volunteerism', 'social impact',
        'corporate citizenship',
    ),
    'Shareholders': (
        'shareholder return', 'shareholder returns', 'stockholder return',
        'stockholder returns', 'shareholder value', 'stockholder value',
        'capital allocation', 'return on invested capital', 'return on equity',
        'earnings per share', 'free cash flow', 'dividends', 'share repurchases',
        'stock repurchases', 'profitability', 'financial discipline',
    ),
}
