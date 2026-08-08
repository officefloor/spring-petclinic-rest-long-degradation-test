package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** membership-number: still '<customerCode>-M<YY>', now over the region-and-hash
 * customerCode. Recomputed from the returned fields. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreMembershipNumberOnRegionHashCode() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		String yy = r.get("registrationDate").asText().substring(2, 4);
		assertEquals(r.get("customerCode").asText() + "-M" + yy, r.get("membershipNumber").asText());
	}
}
