package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** soft-match: the soft-match key (lastName + postcode) is now exactly the
 * household key, so that pair is a household rather than a soft match. A second owner sharing
 * lastName and postcode is a household duplicate (409) unless it declares sharesHousehold, in which
 * case it is created as a household member and is NOT flagged a possible duplicate. (The soundex
 * soft-match returns at , once the household block is folded into the identity key.) */
@Tag("cp35")
class Cp35Tests extends AcceptanceBase {

	@Test
	void coreSharedLastNameAndPostcodeIsHouseholdDuplicate() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // same lastName + postcode, no sharesHousehold -> household duplicate
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityDeclaredHouseholdMemberNotFlagged() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		b.put("sharesHousehold", true); // declared member -> created, not a suspected duplicate
		int id = createOwnerOk(b);
		getOwner(id).andExpect(jsonPath("$.possibleDuplicate").value(false));
	}
}
