package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** household-hash: the household hash reads the structured postcode. Two
 * structured owners with the same lastName + postcode share a householdId. */
@Tag("cp36")
class Cp36Tests extends AcceptanceBase {

	@Test
	void coreHouseholdIdFromStructuredPostcode() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = structuredOwner();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		ObjectNode b = structuredOwner();
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		b.put("sharesHousehold", true);
		assertEquals(fetchOwner(createOwnerOk(a)).get("householdId").asText(),
				fetchOwner(createOwnerOk(b)).get("householdId").asText());
	}
}
