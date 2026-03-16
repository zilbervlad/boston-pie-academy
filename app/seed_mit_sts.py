from app import create_app
from app.extensions import db
from app.models import MITLevelTemplate

app = create_app()

LEVEL_DATA = {
    1: [
        ("Leadership", "Always on time, in Perfect Image, and ensures/enforces TM timeliness"),
        ("Leadership", "Recognizes when to call for help"),
        ("Leadership", "Safety and Security: Dayshift Cashouts"),
        ("Leadership", "Promotes a respectful and inclusive environment for all Team Members"),
        ("Operations", "Certified to open"),
        ("Operations", "Certified to close"),
        ("Operations", "Can make a large Pepperoni in 60 Seconds (has earned 60 second pin)"),
        ("Leadership", "Access store email account; responds when requested"),
        ("Leadership", "Uses Checklist Book and writes in it every shift"),
        ("Leadership", "5 Star Shift"),
        ("Leadership", "Confronts and Corrects Image violations"),
        ("Operations", "Understands and Demonstrates 1-Way Proofing"),
        ("Operations", "Checks in DNC and Coke deliveries, rotates stock"),
        ("Operations", "Enters food deliveries and food transfers into PULSE"),
        ("Operations", "Has taken 5 deliveries and WOWed at the door"),
        ("Operations", "Sanitation, spray bottle, and 2-hour swap"),
        ("Operations", "25 Min ADT Chart (Opens)"),
        ("Operations", "25 Min ADT Chart (Closes)"),
        ("Operations", "PRP: Shifts are always properly prepared"),
        ("Operations", "Has Learned & Demonstrates Basic Load & Go Principles"),
        ("Operations", "Can pass a cut test"),
        ("Operations", "Can perform and sync a self OA"),
        ("Leadership", "Performs 3 Self OA's a week"),
        ("Operations", "Demonstrates Appropriate Scale Usage"),
        ("Training", "Completed all level 1 modules & coaching guides (Adobe MDP Level 1)"),
        ("Training", "DWP Class"),
        ("Training", "Learn how and Close all CCCs"),
        ("Training", "Completed 15 Customer Satisfaction Call Backs"),
        ("Training", "Responded to 10 Negative Tracker Feedback"),
        ("Profits", "Enforces Cash Control Policies & Procedures on Closes"),
        ("Profits", "Complete Level 1 Food Chart (.75%)"),
        ("Profits", "Completed Equipment Maintenance List"),
    ],
    2: [
        ("Leadership", "Motivation Audit Conducted > Score is 3.75 Overall"),
        ("Leadership", "Displays positive energy and passion, motivates the team, offers positive feedback"),
        ("Leadership", "Has sat in on/observed two interviews"),
        ("Leadership", "Has interviewed & hired 2 new team members using the structured interview guide"),
        ("Leadership", "Profesionally enforces all BPI/DPZ Standards"),
        ("Leadership", "Uses DWP procedures appropriately"),
        ("Leadership", "Recognizes & Responds appropriately to store-related issues"),
        ("Leadership", "Communicates regularly with all other memebers of management team"),
        ("Operations", "Demonstrates Advanced Load & Go"),
        ("Profits", "Complete Level 2 Food Chart (.65%)"),
        ("Operations", "Has earned 45 second Large Pepperoni Pin"),
        ("Operations", "Pizza making technique is consistent, can pass 5 out of 5 pizzas"),
        ("Operations", "5 Star shift - Demonstrates 5 Star Attitude"),
        ("Leadership", "Performs and Syncs atleast 3 Self OA's a week"),
        ("Profits", "Uses pulse report and functions to run labor to goal"),
        ("Operations", "Has run shifts in at least three stores"),
        ("Operations", "World's Fastest Pizzamaker in under 2:30"),
        ("Operations", "Completes closing paperwork within one hour"),
        ("Operations", "Can handle a $500 or 60 item hour on ovens"),
        ("Training", "Can Pass FSE Knowledge Quiz"),
        ("Operations", "Certified as Load Captain"),
        ("Operations", "Certified as Go Captain"),
        ("Training", "Completed all level 2 modules & coaching guides (Adobe MDP Level 2)"),
        ("Training", "Has learned and executed 12D Training"),
        ("Training", "Has trained Team Members on Pizza Making"),
        ("Profits", "Learn how to complete an accurate food order"),
        ("Marketing", "LSM Workbook"),
        ("Marketing", "Completes one community involvement activity"),
        ("Training", "Has completed 15 MVP Callbacks"),
    ],
    3: [
        ("Leadership", "Motivation Audit completed with an overall score of 4.0"),
        ("Leadership", "Ensures that all Team Members hustle at all times"),
        ("Leadership", "Displays positive energy and passion, motivates the team, offers positive feedback"),
        ("Leadership", "Demonstrates proper use of DWP to improve behavior"),
        ("Leadership", "Led at least 1 monthly crew meeting"),
        ("Leadership", "Keeps employee communication board current"),
        ("Leadership", "Writes store weekly objectives"),
        ("Leadership", "Understands and Executes ISHCIMTR"),
        ("Leadership", "Has completed one month of the paperwork list"),
        ("Operations", "Completed unannounced OAs on 4 BPI Stores"),
        ("Operations", "Has earned 30 second Large Pepperoni Pin"),
        ("Operations", "Assigns positions/uses position chart for rushes"),
        ("Leadership", "Achieves written objectives for the store"),
        ("Operations", "Can handle a minimum 85 item hour on ovens"),
        ("Operations", "Has 5 shifts using DSS to achieve 15% 1 minute loads"),
        ("Leadership", "Has improved 1 Team Members turn around time or hustle times"),
        ("Leadership", "Has successfully completed a relief management week"),
        ("Marketing", "Understands store's marking plan"),
        ("Marketing", "Creates an incentive for a team upsell contest"),
        ("Marketing", "Completed 1 Advanced community involvement event"),
        ("Leadership", "Handles all customer concerns professionally"),
        ("Training", "Assists in the training of a new MIT"),
        ("Training", "Evaluates Level 1 or 2 MIT"),
        ("Leadership", "Writes an Effective Schedule (4 Weeks)"),
        ("Profits", "Review and analyze store P&L"),
        ("Profits", "Consistently makes accurate food orders"),
        ("Training", "Completed all level 3 modules & coaching guides (Adobe MDP Level 3)"),
    ],
}

with app.app_context():
    print("DB URI:", app.config["SQLALCHEMY_DATABASE_URI"])

    print("Resetting MIT STS templates...")
    MITLevelTemplate.query.delete()
    db.session.commit()

    total = 0
    for level, items in LEVEL_DATA.items():
        for sort_order, (category, item_name) in enumerate(items, start=1):
            template = MITLevelTemplate(
                level_number=level,
                category=category,
                item_name=item_name,
                item_description="",
                sort_order=sort_order,
                is_required=True,
                source_ref=f"MIT STS Level {level}",
            )
            db.session.add(template)
            total += 1

    db.session.commit()

    print(f"Seeded {total} MIT STS template rows.")

    print("Counts by level:")
    for lvl in [1, 2, 3]:
        count = MITLevelTemplate.query.filter_by(level_number=lvl).count()
        print(f"Level {lvl}: {count}")